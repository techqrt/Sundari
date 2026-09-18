from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.wallet.serializers.request.get.get_eligible_tiers import GetEligibleTiersSerializer
from sunndari_apps.wallet.serializers.response.get_all.eligible_tiers import EligibleTiersResponseSerializer
from sunndari_apps.wallet.views.eligible_tiers import EligibleTiersView


class EligibleTiersController:

    @extend_schema(
        description=(
            "List the redemption tiers the customer can currently apply to this booking: "
            "active, affordable in coins, and not exceeding the amount about to be charged."
        ),
        parameters=GetEligibleTiersSerializer.get_parameters(),
        responses=SwaggerPage.response(response=EligibleTiersResponseSerializer),
        tags=['Customers - Wallet'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetEligibleTiersSerializer).validate
    def get_eligible_tiers(request: Request) -> Response:
        return EligibleTiersView().get_extract(params=request.params)
