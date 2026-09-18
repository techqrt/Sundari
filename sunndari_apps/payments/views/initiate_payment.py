import razorpay
from django.db import OperationalError
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.payments.dataclasses.request.create.initiate_payment import InitiatePaymentRequest
from sunndari_apps.wallet.models.redemption_tier import RedemptionTier
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet
from sunndari.constants import Constants


class InitiatePaymentView:

    @staticmethod
    def _debit_redemption_or_fail(**debit_kwargs) -> None:
        """Shared by both places this view debits a redemption's coins. `debit_kwargs`
        must include `payment_id` (also read here, not just passed through, so a
        failure can be recorded against the same payment). A genuine balance problem
        (ValueError) and a lock-contention problem (OperationalError — e.g. SQLite's
        "database is locked" under concurrent requests against the same wallet, or a
        Postgres lock-timeout/serialization failure) are both real possibilities under
        concurrent redemption attempts; either way the payment is marked failed so it
        isn't left 'pending' with a quoted price nothing backs, but OperationalError is
        surfaced as a clean, retry-friendly message rather than the raw driver error
        Common().exception_handler's generic branch would otherwise produce."""
        payment_id = debit_kwargs['payment_id']
        try:
            CustomerWallet.debit(**debit_kwargs)
        except ValueError as e:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(payment_id=payment_id, status_id=failed_status.status_id, failure_reason=str(e)[:300])
            raise
        except OperationalError:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(
                payment_id=payment_id, status_id=failed_status.status_id,
                failure_reason='Wallet was locked by a concurrent request.',
            )
            raise ValueError(Constants.wallet_busy_please_retry)

    @Common().exception_handler
    def initiate_extract(self, params: InitiatePaymentRequest):
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)

        status_name = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if status_name not in Booking.ACTIVE_STATUSES:
            raise ValueError(f"Payment cannot be initiated — booking is '{status_name}'.")

        # Counts cash paid PLUS any coin-redeemed value already settled on a prior
        # successful payment for this booking (e.g. an earlier advance payment that
        # used redemption) — total_paid_for_booking() alone would understate this.
        already_settled = Payment.total_settled_for_booking(booking_id=params.booking_id)
        remaining_due = booking['total_amount'] - already_settled
        if remaining_due <= 0:
            raise ValueError(Constants.payment_already_completed)

        amount = params.amount if params.amount is not None else remaining_due
        if amount <= 0 or amount > remaining_due:
            raise ValueError(Constants.invalid_payment_amount)

        # Commission/payout are always computed off `amount` — the pre-redemption
        # figure — never the post-redemption charge below. A coin redemption is a
        # platform-funded discount: the artist is paid as if the customer paid in full,
        # so redeeming coins never reduces what an artist receives.
        artist = ArtistProfile.objects.filter(artist_id=booking['artist_id']).first()
        commission_amount = round(amount * artist.commission_rate / 100, 2)
        artist_payout_amount = amount - commission_amount

        redemption_tier = None
        charge_amount = amount
        if params.redemption_tier_id is not None:
            redemption_tier = RedemptionTier.objects.filter(
                tier_id=params.redemption_tier_id, is_active=True,
            ).first()
            if not redemption_tier:
                raise ValueError(Constants.redemption_tier_not_found)
            if redemption_tier.rupee_value > amount:
                raise ValueError(Constants.redemption_exceeds_amount)
            charge_amount = amount - redemption_tier.rupee_value

        pending_status = PaymentStatus.objects.filter(name='pending').first()
        payment_id = Payment().create(
            booking_id=params.booking_id,
            customer_id=params.user_id,
            artist_id=booking['artist_id'],
            amount=charge_amount,
            commission_amount=commission_amount,
            artist_payout_amount=artist_payout_amount,
            status_id=pending_status.status_id,
            payment_type=params.payment_type,
        )

        if charge_amount == 0:
            # Fully covered by redeemed coins (redemption_tier.rupee_value == amount —
            # the only way charge_amount can reach exactly 0, since the tier-exceeds-
            # amount check above already rules out a negative charge). There is
            # nothing left for Razorpay to charge, and its Orders API rejects a ₹0
            # order outright, so no gateway call is made at all — the coins are
            # debited and the payment is settled directly.
            self._debit_redemption_or_fail(
                customer_id=params.user_id,
                coins=redemption_tier.coin_cost,
                transaction_type='REDEMPTION',
                booking_id=params.booking_id,
                payment_id=payment_id,
                rupee_equivalent=redemption_tier.rupee_value,
            )
            paid_status = PaymentStatus.objects.filter(name='paid').first()
            Payment.mark_paid_via_wallet(payment_id=payment_id, status_id=paid_status.status_id)
            return Response(
                status=status.HTTP_201_CREATED,
                data=Utils.success_response_data(
                    message='Payment fully covered by redeemed coins — no payment gateway action needed.',
                    data={
                        'payment_id': payment_id,
                        'amount': 0,
                        'currency': Configurations.razorpay_currency,
                        'coins_redeemed': redemption_tier.coin_cost,
                        'redemption_discount': redemption_tier.rupee_value,
                        'fully_covered_by_coins': True,
                    },
                )
            )

        # Razorpay amounts are in the smallest currency unit (paise for INR), never a
        # client-supplied figure — always derived from the same server-authoritative
        # `charge_amount` computed above (already net of any coin redemption).
        amount_in_paise = int(round(charge_amount * 100))
        try:
            razorpay_order = RazorpayGateway.get_client().order.create(data={
                'amount': amount_in_paise,
                'currency': Configurations.razorpay_currency,
                'receipt': f'payment_{payment_id}',
            })
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError) as e:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(payment_id=payment_id, status_id=failed_status.status_id, failure_reason=str(e)[:300])
            raise ValueError('Unable to initiate payment with the payment gateway. Please try again.')

        Payment.set_gateway_order(payment_id=payment_id, gateway='razorpay', gateway_order_id=razorpay_order['id'])

        response_data = {
            'payment_id': payment_id,
            'gateway_order_id': razorpay_order['id'],
            'razorpay_key_id': Configurations.razorpay_key_id,
            'amount': amount_in_paise,
            'currency': Configurations.razorpay_currency,
        }

        if redemption_tier:
            # Coins are only spent once the gateway has actually accepted the order —
            # if RedemptionTier lookup/validation above failed, or the gateway call
            # above failed, no coins were ever touched, so there is nothing to reverse
            # in either of those paths. A failure here (e.g. a genuine balance race)
            # is handled the same way a gateway failure is: mark the payment failed
            # and surface the error, rather than leave a 'pending' payment whose quoted
            # price silently doesn't match what was actually authorized.
            self._debit_redemption_or_fail(
                customer_id=params.user_id,
                coins=redemption_tier.coin_cost,
                transaction_type='REDEMPTION',
                booking_id=params.booking_id,
                payment_id=payment_id,
                rupee_equivalent=redemption_tier.rupee_value,
            )
            response_data['coins_redeemed'] = redemption_tier.coin_cost
            response_data['redemption_discount'] = redemption_tier.rupee_value

        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Payment initiated. Complete payment using the returned order reference.',
                data=response_data,
            )
        )
