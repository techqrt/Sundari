from rest_framework import serializers


class ServiceSubCategorySerializer(serializers.Serializer):
    subCategoryId = serializers.IntegerField()
    categoryId = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, allow_blank=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class ServiceSubCategoryResponseGetSerializer(serializers.Serializer):
    data = ServiceSubCategorySerializer()
