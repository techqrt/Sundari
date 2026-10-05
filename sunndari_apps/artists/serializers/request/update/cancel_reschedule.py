from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.cancel_reschedule import CancelRescheduleRequest


class CancelRescheduleSerializer(serializers.Serializer):
    reschedule_id = serializers.IntegerField()

    def create(self, validated_data) -> CancelRescheduleRequest:
        return CancelRescheduleRequest(**validated_data)
