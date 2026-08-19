from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.help_center.dataclasses.request.get.get_admin_conversation import AdminGetConversationRequest


class AdminGetConversationSerializer(GetSerializer):
    conversation_id = serializers.IntegerField()

    def create(self, validated_data) -> AdminGetConversationRequest:
        return AdminGetConversationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='conversation_id', description='ID of the support conversation',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
