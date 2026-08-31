from rest_framework import serializers


class StartPinSerializer(serializers.Serializer):
    bookingId = serializers.IntegerField()
    startServicePin = serializers.IntegerField()


class StartPinResponseSerializer(serializers.Serializer):
    data = StartPinSerializer()


class CompletionPinSerializer(serializers.Serializer):
    bookingId = serializers.IntegerField()
    completionPin = serializers.IntegerField()


class CompletionPinResponseSerializer(serializers.Serializer):
    data = CompletionPinSerializer()
