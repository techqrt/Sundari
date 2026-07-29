from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.create.initiate_payment import InitiatePaymentSerializer
from sunndari_apps.customers.views.initiate_payment import InitiatePaymentView


class InitiatePaymentController:

    @extend_schema(
        description=(
            'Initiate payment for a booking. Gateway integration (Razorpay/PayU) is not yet '
            'chosen or wired in — this creates a Payment record and returns an internal '
            'placeholder order reference; swap in the real gateway order-creation call once '
            'a provider is confirmed.'
        ),
        request=InitiatePaymentSerializer,
        responses=SwaggerPage.response(description='Payment initiated'),
        tags=['Customers - Payment'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=InitiatePaymentSerializer).validate
    def initiate_payment(request: Request) -> Response:
        return InitiatePaymentView().initiate_extract(params=request.params)
