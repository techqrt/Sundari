from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_salon_addresses import GetSalonAddressesRequest


class GetSalonAddressesSerializer(GetSerializer):
    """No filters: an artist has at most 10 active addresses, so the whole list is returned."""

    def create(self, validated_data) -> GetSalonAddressesRequest:
        return GetSalonAddressesRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
