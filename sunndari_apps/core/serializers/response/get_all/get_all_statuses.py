from rest_framework import serializers


class StatusItemSerializer(serializers.Serializer):
    statusId = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, allow_blank=True)


class StatusListResponseSerializer(serializers.Serializer):
    data = serializers.ListField(child=StatusItemSerializer())
