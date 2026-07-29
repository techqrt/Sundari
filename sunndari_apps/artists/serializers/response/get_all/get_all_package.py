from rest_framework import serializers
from sunndari_apps.artists.serializers.response.get.get_package import PackageSerializer


class PackageGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=PackageSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class PackageResponseGetAllSerializer(serializers.Serializer):
    data = PackageGetAllSerializer()
