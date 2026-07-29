from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.remove_location import RemoveLocationRequest


class RemoveLocationSerializer(serializers.Serializer):
    location_type_id = serializers.IntegerField()

    def create(self, validated_data) -> RemoveLocationRequest:
        return RemoveLocationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='location_type_id', description='Location type ID to remove',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
