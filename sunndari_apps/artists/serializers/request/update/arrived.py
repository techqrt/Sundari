from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.arrived import ArrivedRequest


class ArrivedSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    # No longer required (and ignored if sent): arrival no longer needs the Booking OTP.
    booking_otp = serializers.IntegerField(required=False)

    def create(self, validated_data) -> ArrivedRequest:
        return ArrivedRequest(**validated_data)
