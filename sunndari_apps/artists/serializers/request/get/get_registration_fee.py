from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_registration_fee import GetRegistrationFeeRequest


class GetRegistrationFeeSerializer(GetSerializer):

    def create(self, validated_data) -> GetRegistrationFeeRequest:
        return GetRegistrationFeeRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
