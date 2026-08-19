from rest_framework import serializers
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportConversationSerializer


class SupportConversationGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=SupportConversationSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class SupportConversationResponseGetAllSerializer(serializers.Serializer):
    data = SupportConversationGetAllSerializer()
