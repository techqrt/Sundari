from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_package import DeletePackageRequest


class DeletePackageSerializer(serializers.Serializer):
    package_id = serializers.IntegerField()

    def create(self, validated_data) -> DeletePackageRequest:
        return DeletePackageRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='package_id', description='ID of the package to delete',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
