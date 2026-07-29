from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.customers.serializers.request.get.get_payment import GetPaymentSerializer
from sunndari_apps.customers.serializers.response.get.get_payment import PaymentResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_payment import PaymentResponseGetAllSerializer
from sunndari_apps.customers.views.payment import PaymentView


class PaymentController:

    @extend_schema(
        description='Get a single payment belonging to the logged-in customer.',
        parameters=GetPaymentSerializer.get_parameters(),
        responses=SwaggerPage.response(response=PaymentResponseSerializer),
        tags=['Customers - Payment'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetPaymentSerializer).validate
    def get_payment(request: Request) -> Response:
        return PaymentView().get_extract(params=request.params)

    @extend_schema(
        description='List all payments for the logged-in customer.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=PaymentResponseGetAllSerializer),
        tags=['Customers - Payment'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_payments(request: Request) -> Response:
        return PaymentView().get_all_extract(params=request.params)
