from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_profile import ArtistProfileGetRequest


class ArtistProfileGetSerializer(GetSerializer):
    artist_id = serializers.IntegerField(required=False)

    def create(self, validated_data) -> ArtistProfileGetRequest:
        return ArtistProfileGetRequest(
            artist_id=validated_data.get('artist_id'),
            values=validated_data.get('values', ''),
        )

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='artist_id', description='ID of the artist (omit to get own profile)',
            required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
