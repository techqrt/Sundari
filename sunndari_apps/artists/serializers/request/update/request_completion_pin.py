from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.request_completion_pin import RequestCompletionPinRequest


class RequestCompletionPinSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()

    def create(self, validated_data) -> RequestCompletionPinRequest:
        return RequestCompletionPinRequest(**validated_data)
