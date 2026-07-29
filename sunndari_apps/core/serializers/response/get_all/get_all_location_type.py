from rest_framework import serializers
from sunndari_apps.core.serializers.response.get.get_location_type import LocationTypeSerializer


class LocationTypeGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=LocationTypeSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class LocationTypeResponseGetAllSerializer(serializers.Serializer):
    data = LocationTypeGetAllSerializer()
