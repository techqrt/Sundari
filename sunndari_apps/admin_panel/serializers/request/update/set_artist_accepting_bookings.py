from rest_framework import serializers
from sunndari_apps.admin_panel.dataclasses.request.update.set_artist_accepting_bookings import (
    SetArtistAcceptingBookingsRequest,
)


class SetArtistAcceptingBookingsSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    is_accepting_bookings = serializers.BooleanField()

    def create(self, validated_data) -> SetArtistAcceptingBookingsRequest:
        return SetArtistAcceptingBookingsRequest(**validated_data)
