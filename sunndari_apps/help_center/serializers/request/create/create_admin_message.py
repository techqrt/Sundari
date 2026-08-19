from rest_framework import serializers
from sunndari.config import Configurations
from sunndari_apps.help_center.dataclasses.request.create.create_admin_message import AdminCreateMessageRequest


class AdminCreateMessageSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField()
    content = serializers.CharField(max_length=Configurations.chat_message_max_length)

    def create(self, validated_data) -> AdminCreateMessageRequest:
        return AdminCreateMessageRequest(**validated_data)
