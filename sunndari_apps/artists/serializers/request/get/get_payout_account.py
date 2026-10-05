from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_payout_account import GetPayoutAccountRequest


class GetPayoutAccountSerializer(GetSerializer):

    def create(self, validated_data) -> GetPayoutAccountRequest:
        return GetPayoutAccountRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
