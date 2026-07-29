from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.customers.dataclasses.request.get.get_artist_detail import ArtistDetailRequest


class ArtistDetailSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()

    def create(self, validated_data) -> ArtistDetailRequest:
        return ArtistDetailRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='artist_id', description='ID of the artist to view',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ]
