from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_onboarding_status import GetOnboardingStatusRequest


class GetOnboardingStatusSerializer(GetSerializer):

    def create(self, validated_data) -> GetOnboardingStatusRequest:
        return GetOnboardingStatusRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
