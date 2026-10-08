from rest_framework import serializers


class ServiceSubCategorySerializer(serializers.Serializer):
    # Optional so a request can narrow the columns with `values=`.
    subCategoryId = serializers.IntegerField(required=False)
    categoryId = serializers.IntegerField(required=False)
    categoryName = serializers.CharField(required=False, help_text='Name of the parent service (category)')
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    isActive = serializers.BooleanField(required=False)
    createdAt = serializers.DateTimeField(required=False)
    updatedAt = serializers.DateTimeField(required=False)


class ServiceSubCategoryResponseGetSerializer(serializers.Serializer):
    data = ServiceSubCategorySerializer()
