from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.on_my_way import OnMyWayRequest


class OnMyWaySerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()

    def create(self, validated_data) -> OnMyWayRequest:
        return OnMyWayRequest(**validated_data)
