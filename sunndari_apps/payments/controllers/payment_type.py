from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.core.serializers.request.get.get_no_param import NoParamSerializer
from sunndari_apps.payments.serializers.response.get_all.payment_type import PaymentTypeListResponseSerializer
from sunndari_apps.payments.views.payment_type import PaymentTypeView


class PaymentTypeController:

    @extend_schema(
        description=(
            "Valid values for the `payment_type` field on POST /customers/payments/initiate/. "
            "This is the portion of the booking's total being paid (full/advance/balance), "
            "not the payment method — the gateway checkout UI handles method selection "
            "(UPI, card, netbanking, etc.) and reports it back via webhook, not the client."
        ),
        responses=SwaggerPage.response(response=PaymentTypeListResponseSerializer),
        tags=['Customers - Payment'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=NoParamSerializer).validate
    def get_all_payment_types(request: Request) -> Response:
        return PaymentTypeView().get_all_extract(params=request.params)
