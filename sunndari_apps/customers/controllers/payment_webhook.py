from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.utils import Utils
from sunndari_apps.customers.serializers.request.update.payment_webhook import PaymentWebhookSerializer
from sunndari_apps.customers.views.payment_webhook import PaymentWebhookView


class PaymentWebhookController:

    # Not run through SerializerValidations: that helper stamps request.user.user_id onto
    # params, but a gateway webhook call carries no customer JWT to read a user_id from.

    @extend_schema(
        description=(
            'Payment gateway webhook. STUB: accepts a generic {gateway_order_id, gateway_payment_id, '
            'status} payload with no signature verification — real gateway signature verification '
            'must be added before this goes live, once Razorpay/PayU is confirmed and wired in.'
        ),
        request=PaymentWebhookSerializer,
        responses=SwaggerPage.response(description='Webhook processed'),
        tags=['Customers - Payment'],
    )
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def payment_webhook(request: Request) -> Response:
        serializer = PaymentWebhookSerializer(data=request.data)
        result = Utils().validator(serializer=serializer)
        if isinstance(result, bool):
            params = serializer.create(serializer.validated_data)
            return PaymentWebhookView().webhook_extract(params=params)
        return result
