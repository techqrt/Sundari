from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_booking_status import UpdateBookingStatusRequest


class UpdateBookingStatusSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=['confirmed', 'in_progress', 'completed', 'cancelled', 'no_show'])
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> UpdateBookingStatusRequest:
        return UpdateBookingStatusRequest(**validated_data)
