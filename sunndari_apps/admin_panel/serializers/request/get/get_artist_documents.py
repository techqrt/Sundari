from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.admin_panel.dataclasses.request.get.get_artist_documents import GetArtistDocumentsRequest


class GetArtistDocumentsSerializer(serializers.Serializer):
    artist_id = serializers.IntegerField()

    def create(self, validated_data) -> GetArtistDocumentsRequest:
        return GetArtistDocumentsRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='artist_id', description='Artist whose documents to list', required=True,
            type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
