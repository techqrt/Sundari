from rest_framework import serializers
from sunndari_apps.core.dataclasses.request.get.get_recently_activated_services import RecentlyActivatedServicesRequest


class RecentlyActivatedServicesSerializer(serializers.Serializer):
    """No parameters: the window (15 days) and the clock are the server's, so every client sees the same list."""

    def create(self, validated_data) -> RecentlyActivatedServicesRequest:
        return RecentlyActivatedServicesRequest(**validated_data)
