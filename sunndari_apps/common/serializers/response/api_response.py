from rest_framework import serializers


class ApiResponseSerializer(serializers.Serializer):
    status = serializers.BooleanField()
    message = serializers.CharField()
