from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.payments.serializers.request.update.verify_payment import VerifyPaymentSerializer
from sunndari_apps.payments.views.verify_payment import VerifyPaymentView


class VerifyPaymentController:

    @extend_schema(
        description=(
            'Verify a Razorpay payment after Checkout succeeds. Call this immediately with '
            'the razorpay_order_id/razorpay_payment_id/razorpay_signature returned by the '
            "Checkout handler. The backend independently re-verifies via signature check "
            'and a live Razorpay API fetch before marking the payment paid — a client-side '
            'success callback is never sufficient on its own.'
        ),
        request=VerifyPaymentSerializer,
        responses=SwaggerPage.response(description='Payment verified successfully'),
        tags=['Customers - Payment'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyPaymentSerializer).validate
    def verify_payment(request: Request) -> Response:
        return VerifyPaymentView().verify_extract(params=request.params)
