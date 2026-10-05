from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.get.download_document import DownloadDocumentRequest


class DownloadDocumentSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()
    side = serializers.ChoiceField(choices=['front', 'back'], required=False, default='front')

    def create(self, validated_data) -> DownloadDocumentRequest:
        return DownloadDocumentRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(name='document_id', description='ID of the document', required=True,
                             type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='side', description='front (default) or back', required=False,
                             type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ]
