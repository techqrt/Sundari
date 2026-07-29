from rest_framework import serializers


class ServiceCategorySerializer(serializers.Serializer):
    categoryId = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ServiceCategoryResponseGetSerializer(serializers.Serializer):
    data = ServiceCategorySerializer()
