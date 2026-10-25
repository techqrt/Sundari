import hashlib
import hmac
import json
import logging
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.common.utils import Utils
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.payments.services import PaymentSettlementService

logger = logging.getLogger(__name__)


def _dict(value) -> dict:
    """The value if it is a JSON object, else an empty one, so a payload of the wrong shape reads as "nothing here"
    instead of raising."""
    return value if isinstance(value, dict) else {}


def _text(value, max_length: int = 100) -> str:
    """The value if it is a reasonably short string (every gateway id is), else ''."""
    return value if isinstance(value, str) and len(value) <= max_length else ''


class RazorpayWebhookView:
    """Razorpay's server-to-server notifications. Unlike /verify/ these do not depend on the customer's
    phone: they arrive even if the app was killed right after paying, and they are the gateway's own
    word about its state. Every request must carry a valid HMAC signature of the raw body made with the
    webhook secret; with no secret configured nothing is accepted (an unsigned webhook would let anyone
    mark payments paid).

    Handling is idempotent by construction — Razorpay delivers at-least-once and may repeat or reorder
    events — because each event only moves a payment through PaymentSettlementService / the refund ledger,
    which treat a repeat as a no-op.

    Two kinds of problem are told apart on purpose. An event we can never act on (unrecognised, or a body of the
    wrong shape) is acknowledged with 200 and logged: the gateway retries any non-2xx for about a day, so refusing
    one would only make it repeat the same broken event. A failure on our side (database, etc.) answers 500 so
    the gateway does retry, and no payment is lost."""

    def handle(self, raw_body: bytes, signature: str) -> Response:
        secret = Configurations.razorpay_webhook_secret
        if not secret:
            return Response(
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                data=Utils.error_response_data(Constants.webhook_not_configured, [Constants.webhook_not_configured]),
            )
        if not self._signature_is_valid(raw_body, signature, secret):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=Utils.error_response_data(Constants.webhook_signature_invalid, [Constants.webhook_signature_invalid]),
            )
        try:
            event = json.loads(raw_body)
        except ValueError:
            event = None
        if not isinstance(event, dict):
            logger.warning('Razorpay webhook with a body that is not a JSON object was ignored')
            return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Webhook ignored'))
        try:
            handler = {
                'payment.captured': self._payment_captured,
                'refund.processed': self._refund_processed,
                'refund.failed': self._refund_failed,
            }.get(_text(event.get('event')))
            if handler:
                handler(_dict(event.get('payload')))
        except Exception:
            logger.exception('Razorpay webhook processing failed')
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data=Utils.error_response_data(Constants.server_error, [Constants.server_error]),
            )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Webhook processed'))

    @staticmethod
    def _signature_is_valid(raw_body: bytes, signature: str, secret: str) -> bool:
        """Razorpay signs the exact bytes it sends: HMAC-SHA256 of the body with the webhook secret, hex-encoded.
        Checked here directly (constant-time) rather than through the SDK client, so this security check depends on
        nothing that can be swapped, mocked, or left unconfigured."""
        expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.encode('ascii'), (signature or '').strip().lower().encode('utf-8'))

    def _payment_captured(self, payload: dict) -> None:
        entity = _dict(_dict(payload.get('payment')).get('entity'))
        gateway_payment_id, gateway_order_id = _text(entity.get('id')), _text(entity.get('order_id'))
        if entity.get('status') != 'captured' or not gateway_payment_id or not gateway_order_id:
            return
        payment = Payment.get_by_gateway_order_id(gateway_order_id=gateway_order_id)
        if payment is not None:
            if entity.get('amount') != int(round(payment['amount'] * 100)):
                logger.error('Webhook amount %s does not match payment %s', entity.get('amount'), payment['payment_id'])
                return
            was_paid = PaymentStatus.objects.get(status_id=payment['status_id']).name == 'paid'
            outcome = PaymentSettlementService.apply_solo(payment_id=payment['payment_id'], gateway_payment_id=gateway_payment_id)
            if outcome == PaymentSettlementService.APPLIED and not was_paid:
                NotificationService.notify(
                    user_id=payment['customer_id'], title='Payment status update', type='payment_status',
                    message='Your payment was received successfully.', booking_id=payment['booking_id'],
                )
            return
        order = PaymentOrder.get_by_gateway_order_id(gateway_order_id=gateway_order_id)
        if order is None:
            logger.warning('Webhook for unknown gateway order %s', gateway_order_id)
            return
        if entity.get('amount') != int(round(order['total_amount'] * 100)):
            logger.error('Webhook amount %s does not match order %s', entity.get('amount'), order['order_id'])
            return
        was_paid = PaymentStatus.objects.get(status_id=order['status_id']).name == 'paid'
        outcomes = PaymentSettlementService.apply_group(order_id=order['order_id'], gateway_payment_id=gateway_payment_id)
        if not was_paid:
            applied = [pid for pid, outcome in outcomes.items() if outcome == PaymentSettlementService.APPLIED]
            for booking_id in Payment.objects.filter(payment_id__in=applied).values_list('booking_id', flat=True):
                NotificationService.notify(
                    user_id=order['customer_id'], title='Payment status update', type='payment_status',
                    message='Your payment was received successfully.', booking_id=booking_id,
                )

    def _refund_processed(self, payload: dict) -> None:
        """The gateway finished a refund we asked for: record its id, and close the obligation if the call
        that asked for it never reported success (a lost reply). Only refunds this system made are acted on
        (they carry our payment id in the notes); anything done by hand on the dashboard is left alone."""
        entity = _dict(_dict(payload.get('refund')).get('entity'))
        payment_id = _dict(entity.get('notes')).get('payment_id')
        if not (isinstance(payment_id, (str, int)) and str(payment_id).isdigit() and len(str(payment_id)) <= 18) or not _text(entity.get('id')):
            return
        payment = Payment.objects.select_related('status').filter(payment_id=int(payment_id)).first()
        if payment is None or payment.status.name == 'refunded':
            return
        Payment.objects.filter(payment_id=payment.payment_id).update(
            gateway_refund_id=entity['id'], status_id=PaymentStatus.objects.get(name='refunded').status_id,
            failure_reason=payment.failure_reason if payment.status.name != 'paid' else None,
        )

    def _refund_failed(self, payload: dict) -> None:
        """Nothing to change: the payment is still owed, so the retry job keeps it in its queue. Logged so a
        refund the gateway rejects after accepting the request is visible."""
        entity = _dict(_dict(payload.get('refund')).get('entity'))
        logger.error('Gateway reported refund %s failed (payment notes: %s)', _text(entity.get('id')), _dict(entity.get('notes')))
