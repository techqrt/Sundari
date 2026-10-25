import logging
from django.db import transaction
from django.utils import timezone

from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment, PaymentOrder

logger = logging.getLogger(__name__)


class PaymentSettlementService:
    """Single place that decides what a payment the gateway has captured means for its booking.

    Three things reach this point and must all behave identically: the customer app's /verify/ call, the
    gateway's signed webhook, and the reconciliation job that polls the gateway for payments neither of
    those reported. Keeping the rule in one spot is what makes them safe to run in any order, any number of
    times (every method is idempotent).

    The rule: a capture is applied to its booking only while the booking is still active and the payment
    does not overpay it. Anything else is money the gateway holds but the platform cannot use, so it is
    recorded as an owed refund (never kept, never merely logged) and refunded straight away; the
    retry_owed_refunds job finishes the job if the gateway call fails."""

    APPLIED = 'applied'
    OVERPAID = 'overpaid'
    BOOKING_CLOSED = 'booking_closed'
    UNAPPLIED = 'unapplied'          # already recorded as unapplied (a replay): nothing more to do

    @staticmethod
    def _decide(payment: Payment, booking: Booking) -> str:
        if booking.status.name not in Booking.ACTIVE_STATUSES:
            return PaymentSettlementService.BOOKING_CLOSED
        if Payment.total_settled_for_booking(payment.booking_id) + payment.amount > booking.total_amount:
            return PaymentSettlementService.OVERPAID
        return PaymentSettlementService.APPLIED

    @staticmethod
    def _reason(outcome: str, booking_status: str) -> str:
        if outcome == PaymentSettlementService.OVERPAID:
            return 'Overpayment: captured by the gateway but exceeds the booking total; refund owed'
        return f"Booking was '{booking_status}' when the payment was captured; refund owed"

    @staticmethod
    def _apply_one(payment: Payment, booking: Booking, gateway_payment_id: str, paid_status_id: int, failed_status_id: int) -> str:
        """Caller holds the payment and booking row locks."""
        if payment.status.name == 'paid':
            return PaymentSettlementService.APPLIED
        if payment.status.name in ('refunded', 'partially_refunded') or payment.refund_requested_at is not None:
            return PaymentSettlementService.UNAPPLIED
        outcome = PaymentSettlementService._decide(payment, booking)
        if outcome == PaymentSettlementService.APPLIED:
            Payment.mark_paid(payment_id=payment.payment_id, gateway_payment_id=gateway_payment_id, status_id=paid_status_id)
        else:
            Payment.mark_unapplied_capture(
                payment_id=payment.payment_id, gateway_payment_id=gateway_payment_id, status_id=failed_status_id,
                failure_reason=PaymentSettlementService._reason(outcome, booking.status.name),
            )
            logger.warning(
                'Captured payment %s (gateway %s) not applied to booking %s: %s',
                payment.payment_id, gateway_payment_id, payment.booking_id, outcome,
            )
        return outcome

    @staticmethod
    def refund_unapplied(payment_ids: list) -> None:
        """Starts the refund of captures that were not applied. Runs outside any transaction because it
        calls the gateway; a failure is recorded on the payment and retried by the scheduled job."""
        refunded_status = PaymentStatus.objects.get(name='refunded')
        for payment in Payment.objects.select_related('status').filter(payment_id__in=payment_ids):
            Payment.refund_payment(payment, refunded_status.status_id)

    @staticmethod
    def apply_solo(payment_id: int, gateway_payment_id: str) -> str:
        paid_status = PaymentStatus.objects.get(name='paid')
        failed_status = PaymentStatus.objects.get(name='failed')
        with transaction.atomic():
            payment = Payment.objects.select_for_update().select_related('status').get(payment_id=payment_id)
            booking = Booking.objects.select_for_update().select_related('status').get(booking_id=payment.booking_id)
            outcome = PaymentSettlementService._apply_one(
                payment, booking, gateway_payment_id, paid_status.status_id, failed_status.status_id,
            )
        if outcome in (PaymentSettlementService.OVERPAID, PaymentSettlementService.BOOKING_CLOSED):
            PaymentSettlementService.refund_unapplied([payment_id])
        return outcome

    @staticmethod
    def apply_group(order_id: int, gateway_payment_id: str) -> dict:
        """One gateway transaction pays several bookings, so each booking is judged on its own: those
        that can take their payment keep it, the rest are refunded (a partial refund of the shared gateway
        payment). The order is paid if at least one booking took its share, failed if none did."""
        paid_status = PaymentStatus.objects.get(name='paid')
        failed_status = PaymentStatus.objects.get(name='failed')
        outcomes = {}
        with transaction.atomic():
            order = PaymentOrder.objects.select_for_update().select_related('status').get(order_id=order_id)
            if order.status.name == 'paid':
                return {payment_id: PaymentSettlementService.APPLIED for payment_id in
                        Payment.objects.filter(order_id=order_id).values_list('payment_id', flat=True)}
            for payment in Payment.objects.select_for_update().select_related('status').filter(order_id=order_id).order_by('payment_id'):
                booking = Booking.objects.select_for_update().select_related('status').get(booking_id=payment.booking_id)
                outcomes[payment.payment_id] = PaymentSettlementService._apply_one(
                    payment, booking, gateway_payment_id, paid_status.status_id, failed_status.status_id,
                )
            any_applied = PaymentSettlementService.APPLIED in outcomes.values()
            order.gateway_payment_id = gateway_payment_id
            order.status_id = paid_status.status_id if any_applied else failed_status.status_id
            order.paid_at = timezone.now() if any_applied else None
            order.failure_reason = None if any_applied else 'Captured by the gateway but not applied to any booking; refund owed'
            order.save()
        unapplied = [pid for pid, outcome in outcomes.items()
                     if outcome in (PaymentSettlementService.OVERPAID, PaymentSettlementService.BOOKING_CLOSED)]
        if unapplied:
            PaymentSettlementService.refund_unapplied(unapplied)
        return outcomes
