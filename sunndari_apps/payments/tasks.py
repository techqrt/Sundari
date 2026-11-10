import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from sunndari.config import Configurations
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.payments.services import PaymentSettlementService

logger = logging.getLogger(__name__)


@shared_task
def retry_owed_refunds() -> dict:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). Finishes every refund still owed to a customer —
    the cash a cancelled booking paid, or a gateway capture that could not be applied — with exponential
    backoff per payment, and escalates to the admins instead of retrying forever (Payment.retry_owed_refunds).
    Safe to overlap or re-run: a payment only leaves the queue once the gateway has accepted its refund."""
    return Payment.retry_owed_refunds()


@shared_task
def retry_owed_registration_refunds() -> dict:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). Finishes every artist registration-fee refund still owed
    (a rejected artist's fee, or a capture that could not be applied), with the same backoff and escalation as
    booking refunds. Safe to overlap or re-run."""
    return RegistrationPaymentService.retry_owed_refunds()


def _captured_gateway_payment_id(client, gateway_order_id: str, expected_amount) -> str:
    """The id of the captured gateway payment that fully paid this order, or '' when the order is not paid
    (or the gateway cannot be asked right now). Checked against the amount we quoted, never the gateway's
    word alone."""
    expected_paise = int(round(expected_amount * 100))
    try:
        order = client.order.fetch(gateway_order_id)
        if not (order.get('status') == 'paid' and order.get('amount') == expected_paise
                and order.get('amount_paid') == expected_paise):
            return ''
        for item in client.order.payments(gateway_order_id).get('items', []):
            if item.get('status') == 'captured' and item.get('order_id') == gateway_order_id:
                return item.get('id', '')
    except Exception:
        logger.exception('Could not reconcile gateway order %s', gateway_order_id)
    return ''


@shared_task
def reconcile_pending_payments() -> int:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). A customer can pay and then lose connectivity or
    kill the app before /verify/ is called, and a webhook can be missed; the gateway still holds the money.
    This asks the gateway about every payment that has been waiting longer than the verify call normally
    takes and settles those that are in fact paid, through the same rules /verify/ uses (so one for a
    booking that has since closed is refunded). Returns how many it settled. Orders the customer simply
    never paid stay pending and are left alone."""
    now = timezone.now()
    oldest = now - timedelta(hours=Configurations.payment_reconcile_max_age_hours)
    youngest = now - timedelta(minutes=Configurations.payment_reconcile_min_age_minutes)
    client = RazorpayGateway.get_client()
    settled = 0

    # 'failed' is included: /verify/ marks a payment failed when the gateway had not captured it yet
    # (e.g. authorized, captured a moment later), and such a payment must be able to recover.
    solo = Payment.objects.filter(
        status__name__in=['pending', 'failed'], refund_requested_at__isnull=True, order__isnull=True,
        created_at__gte=oldest, created_at__lte=youngest, gateway_order_id__isnull=False,
    ).exclude(gateway_order_id__startswith='PENDING-').exclude(gateway='wallet')[:200]
    for payment in solo:
        gateway_payment_id = _captured_gateway_payment_id(client, payment.gateway_order_id, payment.amount)
        if gateway_payment_id:
            PaymentSettlementService.apply_solo(payment_id=payment.payment_id, gateway_payment_id=gateway_payment_id)
            settled += 1

    orders = PaymentOrder.objects.filter(
        status__name__in=['pending', 'failed'], created_at__gte=oldest, created_at__lte=youngest,
        gateway_order_id__isnull=False,
    ).exclude(gateway_order_id__startswith='PENDING-')[:200]
    for order in orders:
        gateway_payment_id = _captured_gateway_payment_id(client, order.gateway_order_id, order.total_amount)
        if gateway_payment_id:
            PaymentSettlementService.apply_group(order_id=order.order_id, gateway_payment_id=gateway_payment_id)
            settled += 1

    # Artists' registration-fee payments: same idea, settled through RegistrationPaymentService (a capture
    # the artist cannot use, for instance because the fee was already paid, is refunded there).
    registrations = ArtistRegistrationPayment.objects.filter(
        status__name__in=['pending', 'failed'], paid_at__isnull=True, refund_requested_at__isnull=True,
        gateway='razorpay', gateway_order_id__isnull=False, created_at__gte=oldest, created_at__lte=youngest,
    ).select_related('artist')[:200]
    for registration in registrations:
        gateway_payment_id = _captured_gateway_payment_id(client, registration.gateway_order_id, registration.payable_amount)
        if gateway_payment_id:
            outcome = RegistrationPaymentService.settle(
                registration_payment_id=registration.registration_payment_id, gateway_payment_id=gateway_payment_id,
            )
            if outcome == RegistrationPaymentService.APPLIED:
                RegistrationPaymentService.notify_paid(registration.artist.user_id)
            settled += 1
    return settled
