from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.wallet.dataclasses.request.get.get_wallet import GetWalletRequest


class GetWalletSerializer(GetSerializer):
    def create(self, validated_data) -> GetWalletRequest:
        return GetWalletRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
