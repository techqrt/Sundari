import logging
from datetime import timedelta

import razorpay
from django.db import transaction
from django.utils import timezone

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.promo_code import PromoCode, PromoRedemption
from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment
from sunndari_apps.artists.registration_fee import RegistrationFee
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.payments.gateway import RazorpayGateway

logger = logging.getLogger(__name__)


class RegistrationPaymentService:
    """Starts and finishes an artist's registration payment. Amounts are always worked out by
    RegistrationFee on the server; the only client input is the promo code text."""

    @staticmethod
    def _status(name: str) -> PaymentStatus:
        return PaymentStatus.objects.get(name=name)

    @staticmethod
    def _open_payment(artist_id: int):
        """The artist's payment attempt that is still waiting for money: pending, with a real gateway order,
        and recent enough (the same window as booking payments) that it has not been abandoned."""
        return ArtistRegistrationPayment.objects.select_for_update().filter(
            artist_id=artist_id, status__name='pending', paid_at__isnull=True, gateway_order_id__isnull=False,
            created_at__gte=timezone.now() - timedelta(minutes=Configurations.payment_pending_window_minutes),
        ).order_by('-registration_payment_id').first()

    @staticmethod
    def release(payment: ArtistRegistrationPayment, reason: str) -> None:
        """Gives up on an attempt that took no money: marks it failed and frees its promo reservation so the
        code can be used again. Never touches a payment that is already paid."""
        if payment.paid_at is not None:
            return
        payment.status = RegistrationPaymentService._status('failed')
        payment.failure_reason = reason[:300]
        payment.save(update_fields=['status', 'failure_reason', 'updated_at'])
        PromoRedemption.objects.filter(registration_payment=payment, status='reserved').update(
            status='released', updated_at=timezone.now(),
        )

    @staticmethod
    def complete(payment: ArtistRegistrationPayment, gateway: str, gateway_payment_id: str = None) -> None:
        """Marks the registration paid and makes its promo redemption final. The caller holds the artist's
        row lock. Safe to call twice: a payment that is already paid is left as it is. Any other unpaid
        attempt of the artist is closed, since this one now covers the fee; and a promo that had been freed
        by a replaced attempt is honoured again, because the discounted amount was in fact paid."""
        if payment.paid_at is not None:
            return
        for other in ArtistRegistrationPayment.objects.select_for_update().filter(
            artist_id=payment.artist_id, paid_at__isnull=True,
        ).exclude(pk=payment.pk).filter(status__name='pending'):
            RegistrationPaymentService.release(other, 'Closed: another registration payment was completed')
        payment.status = RegistrationPaymentService._status('paid')
        payment.gateway = gateway
        payment.gateway_payment_id = gateway_payment_id
        payment.paid_at = timezone.now()
        payment.failure_reason = None
        payment.save()
        PromoRedemption.objects.filter(registration_payment=payment).exclude(status='redeemed').update(
            status='redeemed', updated_at=timezone.now(),
        )

    APPLIED = 'applied'
    ALREADY_APPLIED = 'already_applied'   # a repeat: it was applied earlier, so nothing new happened
    REFUND_OWED = 'refund_owed'      # captured by the gateway but not usable: refunded, never kept
    UNAPPLIED = 'unapplied'          # already refunded or being refunded: nothing more to do

    @staticmethod
    def settle(registration_payment_id: int, gateway_payment_id: str) -> str:
        """What a payment the gateway has captured means for the artist's registration. The one place that
        decides it, shared by /verify/ (and the webhook and reconciliation job, which run it too), so they
        are safe in any order and any number of times. Applied only if the artist still owes the fee and has
        not already paid it through another attempt; otherwise the money is recorded as owed back and
        refunded straight away."""
        with transaction.atomic():
            payment = ArtistRegistrationPayment.objects.select_related('status', 'artist').get(
                pk=registration_payment_id,
            )
            profile = ArtistProfile.objects.select_for_update().get(artist_id=payment.artist_id)
            payment = ArtistRegistrationPayment.objects.select_for_update().select_related('status').get(
                pk=registration_payment_id,
            )
            if payment.refund_requested_at is not None or payment.status.name in ('refunded', 'partially_refunded'):
                return RegistrationPaymentService.UNAPPLIED
            if payment.paid_at is not None:
                return RegistrationPaymentService.ALREADY_APPLIED
            already_paid = RegistrationFee.is_paid(profile.artist_id)
            if already_paid or profile.registration_fee_exempt:
                payment.status = RegistrationPaymentService._status('failed')
                payment.gateway = payment.gateway or 'razorpay'
                payment.gateway_payment_id = gateway_payment_id
                payment.refund_requested_at = timezone.now()
                payment.failure_reason = (
                    'Registration fee already paid; refund owed' if already_paid
                    else 'Registration fee not required for this artist; refund owed'
                )
                payment.save()
                PromoRedemption.objects.filter(registration_payment=payment, status='reserved').update(
                    status='released', updated_at=timezone.now(),
                )
                outcome = RegistrationPaymentService.REFUND_OWED
            else:
                RegistrationPaymentService.complete(payment, gateway='razorpay', gateway_payment_id=gateway_payment_id)
                outcome = RegistrationPaymentService.APPLIED
        if outcome == RegistrationPaymentService.REFUND_OWED:
            RegistrationPaymentService.refund(registration_payment_id)
        return outcome

    @staticmethod
    def refund(registration_payment_id: int) -> bool:
        """One refund attempt for a captured registration payment. It becomes 'refunded' only once the gateway
        has accepted the refund; on a failure it keeps its state with the reason and attempt count recorded,
        so the system never claims money was returned when it was not. Returns True when refunded."""
        from sunndari_apps.notifications.utils import NotificationService
        payment = ArtistRegistrationPayment.objects.select_related('status', 'artist').get(pk=registration_payment_id)
        if payment.gateway_refund_id or payment.status.name == 'refunded':
            return True
        now = timezone.now()
        problem = ''
        if payment.gateway == 'razorpay' and payment.gateway_payment_id and payment.payable_amount > 0:
            try:
                refund = RazorpayGateway.get_client().payment.refund(payment.gateway_payment_id, {
                    'amount': int(round(payment.payable_amount * 100)),
                    'notes': {'registration_payment_id': str(payment.registration_payment_id)},
                })
                refund_id = refund.get('id') if isinstance(refund, dict) else None
                if isinstance(refund_id, str):
                    payment.gateway_refund_id = refund_id
            except Exception as error:
                logger.exception('Gateway refund failed for registration payment %s', registration_payment_id)
                problem = f'Refund failed: {str(error)[:200]}'
        if problem:
            ArtistRegistrationPayment.objects.filter(pk=payment.pk).update(
                failure_reason=problem, refund_requested_at=payment.refund_requested_at or now,
                refund_attempts=payment.refund_attempts + 1, refund_last_attempt_at=now, updated_at=now,
            )
            if payment.refund_attempts == 0:
                NotificationService.notify(
                    user_id=payment.artist.user_id, title='Refund being processed',
                    message='We could not return your registration payment automatically yet. Our team will complete the refund.',
                    type='refund_pending',
                )
            return False
        ArtistRegistrationPayment.objects.filter(pk=payment.pk).update(
            status=RegistrationPaymentService._status('refunded'), gateway_refund_id=payment.gateway_refund_id,
            refund_requested_at=payment.refund_requested_at or now, refund_last_attempt_at=now, updated_at=now,
        )
        if payment.payable_amount > 0:
            NotificationService.notify(
                user_id=payment.artist.user_id, title='Refund initiated',
                message=f'A refund of ₹{payment.payable_amount} has been initiated to your original payment method.',
                type='refund_initiated',
            )
        return True

    @staticmethod
    def void_for_rejection(artist_id: int):
        """Called inside the admin's reject transaction. The artist's completed registration payment stops
        counting (so they must pay again to resubmit) and its promo is released for reuse. Returns the payment
        id whose money is now owed back, or None if there was nothing to void. The refund itself is made by
        refund() after the transaction, because it calls the gateway."""
        payment = ArtistRegistrationPayment.objects.select_for_update().filter(
            artist_id=artist_id, paid_at__isnull=False, refund_requested_at__isnull=True,
        ).first()
        if payment is None:
            return None
        payment.refund_requested_at = timezone.now()
        payment.save(update_fields=['refund_requested_at', 'updated_at'])
        PromoRedemption.objects.filter(registration_payment=payment, status__in=['reserved', 'redeemed']).update(
            status='released', updated_at=timezone.now(),
        )
        return payment.pk

    @staticmethod
    def retry_owed_refunds(force: bool = False) -> dict:
        """Finishes every registration refund still owed, with exponential backoff per payment, and escalates
        to the admins exactly once when the attempts run out, as booking refunds do. `force` ignores the
        backoff and the cap. Safe to re-run: a payment leaves the queue only once the gateway accepted it."""
        from sunndari_apps.authentication.models import User
        from sunndari_apps.notifications.models.notification import Notification
        from sunndari_apps.notifications.utils import NotificationService

        now = timezone.now()
        outcome = {'refunded': 0, 'pending': 0, 'waiting': 0, 'escalated': 0}
        owed = ArtistRegistrationPayment.objects.filter(
            refund_requested_at__isnull=False, gateway_refund_id__isnull=True,
        ).exclude(status__name='refunded')
        for payment in owed:
            if not force and payment.refund_attempts >= Configurations.refund_max_attempts:
                outcome['escalated'] += 1
                title = 'Registration refund needs manual attention'
                for admin_id in User.objects.filter(role='admin', is_active=True).values_list('user_id', flat=True):
                    if not Notification.objects.filter(
                        user_id=admin_id, title=title, reference_id=payment.registration_payment_id,
                    ).exists():
                        NotificationService.notify(
                            user_id=admin_id, title=title, type='payment_status',
                            reference_id=payment.registration_payment_id,
                            message=f'Registration payment #{payment.registration_payment_id} (₹{payment.payable_amount}) '
                                    f'could not be refunded after {payment.refund_attempts} attempts: {payment.failure_reason}',
                        )
                continue
            if not force and payment.refund_last_attempt_at:
                wait = min(Configurations.refund_backoff_base_seconds * 2 ** payment.refund_attempts,
                           Configurations.refund_backoff_max_seconds)
                if now < payment.refund_last_attempt_at + timedelta(seconds=wait):
                    outcome['waiting'] += 1
                    continue
            outcome['refunded' if RegistrationPaymentService.refund(payment.registration_payment_id) else 'pending'] += 1
        return outcome

    @staticmethod
    def record_refund_processed(registration_payment_id: int, gateway_refund_id: str) -> None:
        """The gateway finished a refund of a registration payment we asked for: record its id and close the
        obligation, even if the call that asked for it never reported success (a lost reply)."""
        payment = ArtistRegistrationPayment.objects.select_related('status').filter(pk=registration_payment_id).first()
        if payment is None or payment.status.name == 'refunded':
            return
        now = timezone.now()
        ArtistRegistrationPayment.objects.filter(pk=payment.pk).update(
            gateway_refund_id=gateway_refund_id, status=RegistrationPaymentService._status('refunded'),
            refund_requested_at=payment.refund_requested_at or now, updated_at=now,
        )

    @staticmethod
    def notify_paid(user_id: int) -> None:
        from sunndari_apps.notifications.utils import NotificationService
        NotificationService.notify(
            user_id=user_id, title='Registration fee received',
            message='Your registration fee has been received. You can now submit your profile for review.',
            type='payment_status',
        )

    @staticmethod
    def _order_response(payment: ArtistRegistrationPayment) -> dict:
        return {
            'registration_payment_id': payment.registration_payment_id,
            'gateway_order_id': payment.gateway_order_id,
            'razorpay_key_id': Configurations.razorpay_key_id,
            'amount': int(round(payment.payable_amount * 100)),
            'currency': Configurations.razorpay_currency,
            'fee_amount': str(payment.fee_amount),
            'discount_amount': str(payment.discount_amount),
            'payable_amount': str(payment.payable_amount),
            'fully_covered_by_promo': False,
        }

    @staticmethod
    def initiate(user_id: int, promo_code: str = None) -> tuple:
        """Returns (response data, created). An open attempt for the same promo is reused (a double tap or a
        retry must not create a second order); a different promo replaces it. A payable amount of zero is
        completed on the spot with no gateway call."""
        promo_code = (promo_code or '').strip() or None
        free_completion = None
        with transaction.atomic():
            # One registration attempt at a time per artist: everything below queues behind this row lock.
            profile = ArtistProfile.objects.select_for_update().filter(user_id=user_id).first()
            if not profile:
                raise ValueError(Constants.artist_not_found)
            if profile.registration_fee_exempt or RegistrationFee.is_paid(profile.artist_id):
                raise ValueError(Constants.registration_fee_not_required)

            open_payment = RegistrationPaymentService._open_payment(profile.artist_id)
            if open_payment is not None:
                same_promo = (
                    (open_payment.promo.code if open_payment.promo_id else None) == (promo_code.upper() if promo_code else None)
                )
                if same_promo:
                    return RegistrationPaymentService._order_response(open_payment), False
                RegistrationPaymentService.release(open_payment, 'Replaced by a new registration payment attempt')

            # Any other unpaid attempt is abandoned (older than the payment window, or it never got an order).
            # Its promo reservation is freed so the code is not stuck. A late capture for it can still be
            # settled later, as booking payments can.
            for stale in ArtistRegistrationPayment.objects.select_for_update().filter(
                artist_id=profile.artist_id, status__name='pending', paid_at__isnull=True,
            ):
                RegistrationPaymentService.release(stale, 'Abandoned: a new registration payment attempt was started')

            # Lock the promo row so two artists cannot both take the last redemption, then check again.
            if promo_code:
                PromoCode.objects.select_for_update().filter(code=promo_code.upper()).first()
            quote = RegistrationFee.quote(profile.artist_id, promo_code)
            promo = quote['promo']
            payment = ArtistRegistrationPayment.objects.create(
                artist=profile, fee_amount=quote['fee'], discount_percent=quote['discount_percent'],
                discount_amount=quote['discount'], payable_amount=quote['payable'], promo=promo,
                status=RegistrationPaymentService._status('pending'),
            )
            if promo:
                PromoRedemption.objects.create(promo=promo, artist=profile, registration_payment=payment)

            if quote['payable'] <= 0:
                # Nothing to charge, so no gateway order (Razorpay refuses a zero order). The registration is
                # still recorded as a paid payment, and the promo is redeemed.
                RegistrationPaymentService.complete(payment, gateway='promo' if promo else 'free')
                data = RegistrationPaymentService._order_response(payment)
                data.update({
                    'gateway_order_id': None, 'razorpay_key_id': None, 'amount': 0, 'fully_covered_by_promo': True,
                })
                free_completion = data

        if free_completion is not None:
            RegistrationPaymentService.notify_paid(user_id)
            return free_completion, True

        # The gateway is called after the rows are committed, never inside the transaction.
        try:
            order = RazorpayGateway.get_client().order.create(data={
                'amount': int(round(payment.payable_amount * 100)),
                'currency': Configurations.razorpay_currency,
                'receipt': f'registration_{payment.registration_payment_id}',
                'notes': {'artist_id': str(profile.artist_id), 'purpose': 'artist_registration'},
            })
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError) as error:
            with transaction.atomic():
                ArtistProfile.objects.select_for_update().filter(artist_id=profile.artist_id).first()
                RegistrationPaymentService.release(ArtistRegistrationPayment.objects.get(pk=payment.pk), str(error))
            raise ValueError(Constants.registration_gateway_unavailable)
        payment.gateway = 'razorpay'
        payment.gateway_order_id = order['id']
        payment.save(update_fields=['gateway', 'gateway_order_id', 'updated_at'])
        return RegistrationPaymentService._order_response(payment), True
