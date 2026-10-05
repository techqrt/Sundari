from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_addon import GetAddOnRequest


class GetAddOnSerializer(GetSerializer):
    addon_id = serializers.IntegerField()

    def create(self, validated_data) -> GetAddOnRequest:
        return GetAddOnRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='addon_id', description='ID of the add-on',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
