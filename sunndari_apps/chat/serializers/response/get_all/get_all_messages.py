from rest_framework import serializers
from sunndari_apps.chat.serializers.response.get.get_conversation import MessageSerializer


class MessageGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=MessageSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class MessageResponseGetAllSerializer(serializers.Serializer):
    data = MessageGetAllSerializer()
