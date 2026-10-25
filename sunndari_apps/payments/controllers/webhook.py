from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.payments.views.webhook import RazorpayWebhookView


class RazorpayWebhookController:

    @extend_schema(
        description=(
            "Razorpay's server-to-server webhook (payment.captured, refund.processed, refund.failed). Not for the "
            'apps: configure this URL and its secret on the Razorpay dashboard. Authenticated by the HMAC signature in '
            'the X-Razorpay-Signature header, never by a user token.'
        ),
        request=None,
        responses=SwaggerPage.response(description='Webhook processed'),
        tags=['Payment Webhook'],
    )
    @api_view(['POST'])
    @authentication_classes([])
    @permission_classes([AllowAny])
    @throttle_classes([])                  # the gateway's own bursts and retries must never be refused
    def razorpay_webhook(request: Request) -> Response:
        # The signature covers the exact bytes Razorpay sent, so the raw body is read before DRF parses it.
        return RazorpayWebhookView().handle(
            raw_body=request.body, signature=request.headers.get('X-Razorpay-Signature', ''),
        )
