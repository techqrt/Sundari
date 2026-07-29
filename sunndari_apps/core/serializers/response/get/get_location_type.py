from rest_framework import serializers


class LocationTypeSerializer(serializers.Serializer):
    locationTypeId = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class LocationTypeResponseGetSerializer(serializers.Serializer):
    data = LocationTypeSerializer()
