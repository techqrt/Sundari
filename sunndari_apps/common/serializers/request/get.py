from rest_framework import serializers


class GetSerializer(serializers.Serializer):
    values = serializers.CharField(max_length=200, required=False, default='')
