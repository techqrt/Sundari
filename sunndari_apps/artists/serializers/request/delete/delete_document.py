from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_document import DeleteDocumentRequest


class DeleteDocumentSerializer(serializers.Serializer):
    document_id = serializers.IntegerField()

    def create(self, validated_data) -> DeleteDocumentRequest:
        return DeleteDocumentRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='document_id', description='ID of the document to delete',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
