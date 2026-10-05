from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.upload_package_photo import UploadPackagePhotoRequest


class UploadPackagePhotoSerializer(serializers.Serializer):
    """Multipart: `package_id` plus the image in the `photo` file field."""
    package_id = serializers.IntegerField()

    def create(self, validated_data) -> UploadPackagePhotoRequest:
        return UploadPackagePhotoRequest(**validated_data)
