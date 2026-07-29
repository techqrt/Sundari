from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.delete.remove_service import RemoveServiceRequest


class RemoveServiceSerializer(serializers.Serializer):
    sub_category_id = serializers.IntegerField()

    def create(self, validated_data) -> RemoveServiceRequest:
        return RemoveServiceRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='sub_category_id', description='Sub-category ID to remove',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
