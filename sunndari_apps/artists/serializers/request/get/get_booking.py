from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_booking import GetArtistBookingRequest


class GetArtistBookingSerializer(GetSerializer):
    booking_id = serializers.IntegerField()
    filter_key = serializers.CharField(max_length=100, required=False, default='')
    filter_value = serializers.CharField(max_length=100, required=False, default='')

    def create(self, validated_data) -> GetArtistBookingRequest:
        return GetArtistBookingRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='booking_id', description='ID of the booking',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='filter_key', description="Optional: 'paymentStatus' with filter_value 'paid' or 'unpaid' — the booking is returned only if it matches",
            required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='filter_value', description="'paid' or 'unpaid' (used with filter_key=paymentStatus)",
            required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
        ))
        return params
