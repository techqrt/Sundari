from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.set_schedule import SetScheduleRequest


class SetScheduleSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    location_type_id = serializers.IntegerField(required=False, allow_null=True)

    def create(self, validated_data) -> SetScheduleRequest:
        return SetScheduleRequest(
            day_of_week=validated_data['day_of_week'],
            start_time=str(validated_data['start_time']),
            end_time=str(validated_data['end_time']),
            location_type_id=validated_data.get('location_type_id'),
        )
