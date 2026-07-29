from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.customers.dataclasses.request.get.check_availability import CheckAvailabilityRequest


class CheckAvailabilitySerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    booking_date = serializers.DateField(input_formats=['%d-%m-%y'])

    def create(self, validated_data) -> CheckAvailabilityRequest:
        return CheckAvailabilityRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='artist_id', description='ID of the artist to check',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name='booking_date', description='Date to check (DD-MM-YY)',
                required=True, type=OpenApiTypes.DATE, location=OpenApiParameter.QUERY,
            ),
        ]
