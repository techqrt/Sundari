from rest_framework import serializers
from sunndari_apps.admin_panel.dataclasses.request.update.reject_artist import RejectArtistRequest


class RejectArtistSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> RejectArtistRequest:
        return RejectArtistRequest(**validated_data)
