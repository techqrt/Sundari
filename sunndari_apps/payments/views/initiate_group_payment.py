import razorpay
from django.db import OperationalError, transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.payments.dataclasses.request.create.initiate_group_payment import InitiateGroupPaymentRequest
from sunndari_apps.wallet.models.redemption_tier import RedemptionTier
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet
from sunndari.constants import Constants


class InitiateGroupPaymentView:

    @Common().exception_handler
    def initiate_group_extract(self, params: InitiateGroupPaymentRequest):
        booking_ids = params.booking_ids
        if len(set(booking_ids)) != len(booking_ids):
            raise ValueError(Constants.duplicate_booking_in_group)

        # Validate every booking up front, before creating anything — a single bad
        # booking_id anywhere in the list must not leave a PaymentOrder or any Payment
        # rows behind for the ones that were valid.
        pending_status = PaymentStatus.objects.filter(name='pending').first()
        entries = []
        for booking_id in booking_ids:
            booking = Booking.get(booking_id=booking_id)
            if not booking or booking['customer_id'] != params.user_id:
                raise ValueError(f"Booking #{booking_id} not found.")

            status_name = BookingStatus.objects.filter(
                status_id=booking['status_id'],
            ).values_list('name', flat=True).first()
            if status_name not in Booking.ACTIVE_STATUSES:
                raise ValueError(f"Payment cannot be initiated — booking #{booking_id} is '{status_name}'.")

            # Group payments are always "full" for each booking (see InitiatePaymentView
            # for the payment_type/partial-amount option on a solo payment) — every
            # booking in the group is settled completely in this one checkout.
            already_settled = Payment.total_settled_for_booking(booking_id=booking_id)
            remaining_due = booking['total_amount'] - already_settled
            if remaining_due <= 0:
                raise ValueError(f"Booking #{booking_id} is already fully paid.")

            # charge_amount is what's actually collected for this booking (post-
            # redemption); amount stays the pre-redemption figure commission/payout are
            # computed from. Only entries[0] (booking_ids[0]) can ever have these differ
            # — see the redemption block below.
            entries.append({'booking': booking, 'amount': remaining_due, 'charge_amount': remaining_due})

        # Redemption is only ever applied to booking_ids[0] — the whole discount has to
        # come off one booking's Payment.amount (it can't go negative), so the tier's
        # rupee value is capped at that one booking's own remaining-due amount, exactly
        # like a solo /initiate/ payment. The other bookings in the group are always
        # charged in full. Use GET /eligible_tiers/?booking_id=<booking_ids[0]> to source
        # the tier list for this — it already validates against that exact amount.
        redemption_tier = None
        if params.redemption_tier_id is not None:
            redemption_tier = RedemptionTier.objects.filter(
                tier_id=params.redemption_tier_id, is_active=True,
            ).first()
            if not redemption_tier:
                raise ValueError(Constants.redemption_tier_not_found)
            first_entry = entries[0]
            if redemption_tier.rupee_value > first_entry['amount']:
                raise ValueError(Constants.redemption_exceeds_amount)
            first_entry['charge_amount'] = first_entry['amount'] - redemption_tier.rupee_value

        total_amount = sum(entry['charge_amount'] for entry in entries)

        with transaction.atomic():
            order_id = PaymentOrder().create(
                customer_id=params.user_id, total_amount=total_amount, status_id=pending_status.status_id,
            )
            payment_ids = []
            first_booking_payment_id = None
            for index, entry in enumerate(entries):
                booking = entry['booking']
                amount = entry['amount']
                charge_amount = entry['charge_amount']
                # Commission/payout are always computed off the PRE-redemption `amount`
                # — the platform absorbs the discount, never the artist (same rule as
                # a solo redeemed payment).
                artist = ArtistProfile.objects.filter(artist_id=booking['artist_id']).first()
                commission_amount = round(amount * artist.commission_rate / 100, 2)
                artist_payout_amount = amount - commission_amount
                payment_id = Payment().create(
                    booking_id=booking['booking_id'],
                    customer_id=params.user_id,
                    artist_id=booking['artist_id'],
                    amount=charge_amount,
                    commission_amount=commission_amount,
                    artist_payout_amount=artist_payout_amount,
                    status_id=pending_status.status_id,
                    payment_type='full',
                    order_id=order_id,
                )
                payment_ids.append(payment_id)
                if index == 0:
                    first_booking_payment_id = payment_id

        # Razorpay amounts are in paise, never a client-supplied figure — always the
        # sum of the same server-authoritative per-booking charge amounts above (already
        # net of any redemption on the first booking). Given a group always has at least
        # 2 bookings and only the first can ever be discounted, this total can never
        # reach 0 — there is always something left to charge via the gateway.
        amount_in_paise = int(round(total_amount * 100))
        try:
            razorpay_order = RazorpayGateway.get_client().order.create(data={
                'amount': amount_in_paise,
                'currency': Configurations.razorpay_currency,
                'receipt': f'payment_order_{order_id}',
            })
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError) as e:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            PaymentOrder.mark_failed(order_id=order_id, status_id=failed_status.status_id, failure_reason=str(e)[:300])
            raise ValueError('Unable to initiate payment with the payment gateway. Please try again.')

        PaymentOrder.set_gateway_order(order_id=order_id, gateway='razorpay', gateway_order_id=razorpay_order['id'])

        response_data = {
            'order_id': order_id,
            'payment_ids': payment_ids,
            'gateway_order_id': razorpay_order['id'],
            'razorpay_key_id': Configurations.razorpay_key_id,
            'amount': amount_in_paise,
            'currency': Configurations.razorpay_currency,
        }

        if redemption_tier:
            # Coins are only spent once the gateway has actually accepted the order —
            # same reasoning as the solo flow. A failure here fails the whole group
            # (order + every Payment under it), not just the first booking's, since
            # they all share one Razorpay order that has already been created.
            try:
                CustomerWallet.debit(
                    customer_id=params.user_id,
                    coins=redemption_tier.coin_cost,
                    transaction_type='REDEMPTION',
                    booking_id=booking_ids[0],
                    payment_id=first_booking_payment_id,
                    rupee_equivalent=redemption_tier.rupee_value,
                )
            except ValueError as e:
                failed_status = PaymentStatus.objects.filter(name='failed').first()
                PaymentOrder.mark_failed(order_id=order_id, status_id=failed_status.status_id, failure_reason=str(e)[:300])
                raise
            except OperationalError:
                failed_status = PaymentStatus.objects.filter(name='failed').first()
                PaymentOrder.mark_failed(
                    order_id=order_id, status_id=failed_status.status_id,
                    failure_reason='Wallet was locked by a concurrent request.',
                )
                raise ValueError(Constants.wallet_busy_please_retry)
            response_data['coins_redeemed'] = redemption_tier.coin_cost
            response_data['redemption_discount'] = redemption_tier.rupee_value

        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Payment initiated. Complete payment using the returned order reference.',
                data=response_data,
            )
        )
