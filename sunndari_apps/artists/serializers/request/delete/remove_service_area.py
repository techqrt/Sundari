from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.remove_service_area import RemoveServiceAreaRequest


class RemoveServiceAreaSerializer(serializers.Serializer):
    area_id = serializers.IntegerField()

    def create(self, validated_data) -> RemoveServiceAreaRequest:
        return RemoveServiceAreaRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='area_id', description='ID of the service area to remove',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
