from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.update.cancel_booking import CancelBookingRequest


class CancelBookingSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> CancelBookingRequest:
        return CancelBookingRequest(**validated_data)
