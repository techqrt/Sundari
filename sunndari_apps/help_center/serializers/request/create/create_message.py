from rest_framework import serializers
from sunndari.config import Configurations
from sunndari_apps.help_center.dataclasses.request.create.create_message import CreateMessageRequest


class SupportCreateMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=Configurations.chat_message_max_length)
    subject = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)

    def create(self, validated_data) -> CreateMessageRequest:
        return CreateMessageRequest(**validated_data)
