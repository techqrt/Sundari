from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.core.dataclasses.request.get.get_service_sub_category import ServiceSubCategoryGetRequest


class ServiceSubCategoryGetSerializer(GetSerializer):
    sub_category_id = serializers.IntegerField()

    def create(self, validated_data) -> ServiceSubCategoryGetRequest:
        return ServiceSubCategoryGetRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='sub_category_id', description='ID of the service sub-category',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
