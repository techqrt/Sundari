from rest_framework import serializers
from sunndari.config import Configurations
from sunndari_apps.chat.dataclasses.request.create.create_message import CreateMessageRequest


class CreateMessageSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    content = serializers.CharField(max_length=Configurations.chat_message_max_length)

    def create(self, validated_data) -> CreateMessageRequest:
        return CreateMessageRequest(**validated_data)
