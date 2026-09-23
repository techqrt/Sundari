from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.payments.serializers.request.create.initiate_group_payment import InitiateGroupPaymentSerializer
from sunndari_apps.payments.views.initiate_group_payment import InitiateGroupPaymentView


class InitiateGroupPaymentController:

    @extend_schema(
        description=(
            "Initiate a single payment covering multiple bookings at once (e.g. a "
            "multi-quantity booking flow that created several booking_ids) — one shared "
            "Razorpay order for the combined total, with one Payment row created per "
            "booking underneath it. Each booking is always paid in full; for a partial "
            "(advance/balance) payment on a single booking, use /initiate/ instead."
        ),
        request=InitiateGroupPaymentSerializer,
        responses=SwaggerPage.response(description='Group payment initiated'),
        tags=['Customers - Payment'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=InitiateGroupPaymentSerializer).validate
    def initiate_group_payment(request: Request) -> Response:
        return InitiateGroupPaymentView().initiate_group_extract(params=request.params)
