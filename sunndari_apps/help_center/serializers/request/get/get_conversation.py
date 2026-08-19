from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.help_center.dataclasses.request.get.get_conversation import GetConversationRequest


class SupportGetConversationSerializer(GetSerializer):

    def create(self, validated_data) -> GetConversationRequest:
        return GetConversationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return SwaggerPage.get_parameters()
