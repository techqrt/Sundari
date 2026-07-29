from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.remove_schedule import RemoveScheduleRequest


class RemoveScheduleSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)

    def create(self, validated_data) -> RemoveScheduleRequest:
        return RemoveScheduleRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='day_of_week', description='Day to remove (0=Mon, 6=Sun)',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
