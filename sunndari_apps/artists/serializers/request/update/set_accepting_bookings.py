from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.set_accepting_bookings import SetAcceptingBookingsRequest


class SetAcceptingBookingsSerializer(serializers.Serializer):
    is_accepting_bookings = serializers.BooleanField()

    def create(self, validated_data) -> SetAcceptingBookingsRequest:
        return SetAcceptingBookingsRequest(**validated_data)
