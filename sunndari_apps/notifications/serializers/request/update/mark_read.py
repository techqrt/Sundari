from rest_framework import serializers
from sunndari_apps.notifications.dataclasses.request.update.mark_read import MarkReadRequest


class MarkReadSerializer(serializers.Serializer):
    notification_id = serializers.IntegerField()

    def create(self, validated_data) -> MarkReadRequest:
        return MarkReadRequest(**validated_data)
