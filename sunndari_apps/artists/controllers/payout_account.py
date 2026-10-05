from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.artists.serializers.request.create.set_payout_account import SetPayoutAccountSerializer
from sunndari_apps.artists.serializers.request.get.get_payout_account import GetPayoutAccountSerializer
from sunndari_apps.artists.serializers.response.get.get_payout_account import PayoutAccountResponseSerializer
from sunndari_apps.artists.views.payout_account import ArtistPayoutAccountView


class ArtistPayoutAccountController:

    @extend_schema(
        description='Set (create or update) the artist payout bank account. One account per artist.',
        request=SetPayoutAccountSerializer,
        responses=SwaggerPage.response(description='Payout account saved successfully'),
        tags=['Artists - Onboarding'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SetPayoutAccountSerializer).validate
    def set_payout_account(request: Request) -> Response:
        return ArtistPayoutAccountView().set_extract(params=request.params)

    @extend_schema(
        description='Get own payout account. The bank account number is returned masked.',
        parameters=GetPayoutAccountSerializer.get_parameters(),
        responses=SwaggerPage.response(response=PayoutAccountResponseSerializer),
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetPayoutAccountSerializer).validate
    def get_payout_account(request: Request) -> Response:
        return ArtistPayoutAccountView().get_extract(params=request.params)
