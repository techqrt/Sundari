from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.payment import Payment
from sunndari_apps.customers.dataclasses.request.update.payment_webhook import PaymentWebhookRequest
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class PaymentWebhookView:

    @Common().exception_handler
    def webhook_extract(self, params: PaymentWebhookRequest):
        payment = Payment.get_by_gateway_order_id(gateway_order_id=params.gateway_order_id)
        if not payment:
            raise ValueError(Constants.payment_not_found)

        if params.status == 'paid':
            paid_status = PaymentStatus.objects.filter(name='paid').first()
            Payment.mark_paid(
                payment_id=payment['payment_id'],
                gateway_payment_id=params.gateway_payment_id,
                status_id=paid_status.status_id,
            )
            notify_message = 'Your payment was received successfully.'
        else:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(
                payment_id=payment['payment_id'],
                status_id=failed_status.status_id,
                failure_reason=params.reason or None,
            )
            notify_message = 'Your payment attempt failed.'

        NotificationService.notify(
            user_id=payment['customer_id'],
            title='Payment status update',
            message=notify_message,
            type='payment_status',
            booking_id=payment['booking_id'],
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Webhook processed')
        )
