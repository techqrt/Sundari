from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.arrived import ArrivedRequest


class ArrivedSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    booking_otp = serializers.IntegerField()

    def create(self, validated_data) -> ArrivedRequest:
        return ArrivedRequest(**validated_data)
