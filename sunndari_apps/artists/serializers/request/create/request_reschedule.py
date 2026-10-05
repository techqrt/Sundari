from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.request_reschedule import RequestRescheduleRequest


class RequestRescheduleSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    proposed_date = serializers.DateField(input_formats=['%d-%m-%y'])
    proposed_start_time = serializers.TimeField()
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> RequestRescheduleRequest:
        return RequestRescheduleRequest(**validated_data)
