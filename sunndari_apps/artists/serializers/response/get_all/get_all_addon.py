from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_addon import AddOnSerializer


class AddOnGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=AddOnSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class AddOnResponseGetAllSerializer(serializers.Serializer):
    data = AddOnGetAllSerializer()
