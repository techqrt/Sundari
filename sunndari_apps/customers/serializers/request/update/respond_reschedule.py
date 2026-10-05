from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.update.respond_reschedule import RespondRescheduleRequest


class RespondRescheduleSerializer(serializers.Serializer):
    reschedule_id = serializers.IntegerField()
    decision = serializers.ChoiceField(choices=['accepted', 'rejected'])

    def create(self, validated_data) -> RespondRescheduleRequest:
        return RespondRescheduleRequest(**validated_data)
