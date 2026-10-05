from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_profile_photo import DeleteProfilePhotoRequest


class DeleteProfilePhotoSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['profile', 'cover'])

    def create(self, validated_data) -> DeleteProfilePhotoRequest:
        return DeleteProfilePhotoRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='kind', description='profile or cover', required=True,
            type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
        )]
