from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileSerializer


class ArtistProfileGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ArtistProfileSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ArtistProfileResponseGetAllSerializer(serializers.Serializer):
    data = ArtistProfileGetAllSerializer()
