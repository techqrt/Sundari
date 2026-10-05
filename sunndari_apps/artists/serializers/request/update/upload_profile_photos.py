from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.upload_profile_photos import UploadProfilePhotosRequest


class UploadProfilePhotosSerializer(serializers.Serializer):
    """Multipart only: the images arrive as `profile_photo` and/or `cover_photo` files."""

    def create(self, validated_data) -> UploadProfilePhotosRequest:
        return UploadProfilePhotosRequest(**validated_data)
