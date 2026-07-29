from rest_framework import serializers
from sunndari_apps.notifications.dataclasses.request.update.mark_all_read import MarkAllReadRequest


class MarkAllReadSerializer(serializers.Serializer):

    def create(self, validated_data) -> MarkAllReadRequest:
        return MarkAllReadRequest()
