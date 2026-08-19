from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.help_center.dataclasses.request.update.close_conversation import CloseConversationRequest


class CloseConversationSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField()

    def create(self, validated_data) -> CloseConversationRequest:
        return CloseConversationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='conversation_id', description='ID of the support conversation',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
