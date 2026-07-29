from rest_framework import serializers
from sunndari_apps.core.serializers.response.get.get_service_sub_category import ServiceSubCategorySerializer


class ServiceSubCategoryGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ServiceSubCategorySerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ServiceSubCategoryResponseGetAllSerializer(serializers.Serializer):
    data = ServiceSubCategoryGetAllSerializer()
