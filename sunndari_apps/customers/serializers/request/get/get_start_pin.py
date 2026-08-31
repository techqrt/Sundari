from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.customers.dataclasses.request.get.get_start_pin import GetStartPinRequest


class GetStartPinSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()

    def create(self, validated_data) -> GetStartPinRequest:
        return GetStartPinRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='booking_id', description='ID of the booking',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ]
