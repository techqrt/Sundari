from rest_framework import serializers
from sunndari_apps.core.serializers.response.get.get_service_category import ServiceCategorySerializer


class ServiceCategoryGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=ServiceCategorySerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class ServiceCategoryResponseGetAllSerializer(serializers.Serializer):
    data = ServiceCategoryGetAllSerializer()
