from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.core.dataclasses.request.get.get_service_category import ServiceCategoryGetRequest


class ServiceCategoryGetSerializer(GetSerializer):
    category_id = serializers.IntegerField()

    def create(self, validated_data) -> ServiceCategoryGetRequest:
        return ServiceCategoryGetRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='category_id', description='ID of the service category',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
