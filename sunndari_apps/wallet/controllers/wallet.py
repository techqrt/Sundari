from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.wallet.serializers.request.get.get_wallet import GetWalletSerializer
from sunndari_apps.wallet.serializers.response.get.wallet import WalletResponseSerializer
from sunndari_apps.wallet.serializers.response.get_all.transaction import TransactionResponseGetAllSerializer
from sunndari_apps.wallet.views.wallet import WalletView


class WalletController:

    @extend_schema(
        description="Get the logged-in customer's coin wallet balance.",
        parameters=GetWalletSerializer.get_parameters(),
        responses=SwaggerPage.response(response=WalletResponseSerializer),
        tags=['Customers - Wallet'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetWalletSerializer).validate
    def get_wallet(request: Request) -> Response:
        return WalletView().get_extract(params=request.params)

    @extend_schema(
        description="List the logged-in customer's coin transaction history (cashback, redemptions, reversals, expiry, adjustments).",
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=TransactionResponseGetAllSerializer),
        tags=['Customers - Wallet'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_transactions(request: Request) -> Response:
        return WalletView().get_all_transactions_extract(params=request.params)
