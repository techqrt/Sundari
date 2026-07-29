from rest_framework import serializers
from sunndari_apps.customers.serializers.response.get.search_artist import ArtistSearchResultSerializer


class ArtistSearchGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ArtistSearchResultSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ArtistSearchResponseGetAllSerializer(serializers.Serializer):
    data = ArtistSearchGetAllSerializer()
