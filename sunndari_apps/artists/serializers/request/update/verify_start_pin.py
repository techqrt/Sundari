from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.verify_start_pin import VerifyStartPinRequest


class VerifyStartPinSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    start_service_pin = serializers.IntegerField()

    def create(self, validated_data) -> VerifyStartPinRequest:
        return VerifyStartPinRequest(**validated_data)
