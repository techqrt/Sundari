from rest_framework import serializers
from sunndari_apps.admin_panel.dataclasses.request.update.approve_artist import ApproveArtistRequest


class ApproveArtistSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> ApproveArtistRequest:
        return ApproveArtistRequest(**validated_data)
