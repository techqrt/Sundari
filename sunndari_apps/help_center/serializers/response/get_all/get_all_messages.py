from rest_framework import serializers
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportMessageSerializer


class SupportMessageGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=SupportMessageSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class SupportMessageResponseGetAllSerializer(serializers.Serializer):
    data = SupportMessageGetAllSerializer()
