from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.chat.dataclasses.request.get.get_conversation import GetConversationRequest


class GetConversationSerializer(GetSerializer):
    booking_id = serializers.IntegerField()

    def create(self, validated_data) -> GetConversationRequest:
        return GetConversationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='booking_id', description='ID of the booking',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
