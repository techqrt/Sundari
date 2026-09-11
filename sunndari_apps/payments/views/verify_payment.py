import razorpay
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.payments.models import Payment
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.payments.dataclasses.request.update.verify_payment import VerifyPaymentRequest
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class VerifyPaymentView:
    """No webhook is used in this integration (deliberate — see plan discussion). This
    endpoint is the sole confirmation path: the customer app calls it right after
    Razorpay Checkout succeeds, and it independently re-establishes that the payment is
    real via two separate checks — a cryptographic signature check (proves the values
    weren't fabricated by the client, since only Razorpay and this server's key_secret
    can produce a valid one) and a live Razorpay API fetch (proves the payment actually
    exists and was captured, not just that the signature format was well-formed)."""

    @Common().exception_handler
    def verify_extract(self, params: VerifyPaymentRequest):
        payment = Payment.get_by_gateway_order_id(gateway_order_id=params.razorpay_order_id)
        if not payment or payment['customer_id'] != params.user_id:
            raise ValueError(Constants.payment_not_found)

        current_status = PaymentStatus.objects.filter(
            status_id=payment['status_id'],
        ).values_list('name', flat=True).first()

        # Idempotent: a repeat call (retry after a flaky response, duplicate tap, etc.)
        # on an already-verified payment is a safe no-op, not an error.
        if current_status == 'paid':
            return Response(
                status=status.HTTP_200_OK,
                data=Utils.success_response_data(message='Payment already verified')
            )
        if current_status in ('refunded', 'partially_refunded'):
            raise ValueError(Constants.payment_not_verifiable)

        client = RazorpayGateway.get_client()

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': params.razorpay_order_id,
                'razorpay_payment_id': params.razorpay_payment_id,
                'razorpay_signature': params.razorpay_signature,
            })
        except razorpay.errors.SignatureVerificationError:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(
                payment_id=payment['payment_id'], status_id=failed_status.status_id,
                failure_reason='Signature verification failed',
            )
            raise ValueError(Constants.payment_signature_invalid)

        # Signature alone proves the triple wasn't fabricated by the client — it does not
        # prove the payment was actually captured (e.g. it could be an authorized-but-not-
        # yet-captured payment on some flows). Independently confirm via the Razorpay API
        # itself rather than trusting the client's report of success.
        try:
            razorpay_payment = client.payment.fetch(params.razorpay_payment_id)
            razorpay_order = client.order.fetch(params.razorpay_order_id)
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError):
            raise ValueError(Constants.payment_verification_mismatch)

        # Validate against the ORDER's amount, not the payment's charged amount: when an
        # account is configured to pass the gateway fee to the customer, Razorpay adds
        # that surcharge on top at charge time, so payment.amount can legitimately exceed
        # the order amount we set at creation. The order's own amount/amount_paid can't be
        # inflated by the client, so it's the correct field to check for tampering.
        expected_amount_paise = int(round(payment['amount'] * 100))
        is_valid = (
            razorpay_payment.get('order_id') == params.razorpay_order_id
            and razorpay_payment.get('status') == 'captured'
            and razorpay_order.get('amount') == expected_amount_paise
            and razorpay_order.get('amount_paid') == razorpay_order.get('amount')
            and razorpay_order.get('status') == 'paid'
        )
        if not is_valid:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(
                payment_id=payment['payment_id'], status_id=failed_status.status_id,
                failure_reason=(
                    f"Gateway reported payment status='{razorpay_payment.get('status')}', "
                    f"order status='{razorpay_order.get('status')}'"
                ),
            )
            raise ValueError(Constants.payment_verification_mismatch)

        paid_status = PaymentStatus.objects.filter(name='paid').first()
        Payment.mark_paid(
            payment_id=payment['payment_id'],
            gateway_payment_id=params.razorpay_payment_id,
            status_id=paid_status.status_id,
        )
        NotificationService.notify(
            user_id=payment['customer_id'],
            title='Payment status update',
            message='Your payment was received successfully.',
            type='payment_status',
            booking_id=payment['booking_id'],
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Payment verified successfully')
        )
