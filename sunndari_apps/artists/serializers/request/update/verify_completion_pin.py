from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.verify_completion_pin import VerifyCompletionPinRequest


class VerifyCompletionPinSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    completion_pin = serializers.IntegerField()

    def create(self, validated_data) -> VerifyCompletionPinRequest:
        return VerifyCompletionPinRequest(**validated_data)
