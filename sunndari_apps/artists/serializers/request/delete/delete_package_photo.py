from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_package_photo import DeletePackagePhotoRequest


class DeletePackagePhotoSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()

    def create(self, validated_data) -> DeletePackagePhotoRequest:
        return DeletePackagePhotoRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='package_id', description='Package whose photo to remove',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
