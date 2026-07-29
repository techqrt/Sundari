from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.core.dataclasses.request.get.get_location_type import LocationTypeGetRequest


class LocationTypeGetSerializer(GetSerializer):
    location_type_id = serializers.IntegerField()

    def create(self, validated_data) -> LocationTypeGetRequest:
        return LocationTypeGetRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='location_type_id', description='ID of the location type',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
