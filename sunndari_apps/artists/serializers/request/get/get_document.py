from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.artists.dataclasses.request.get.get_document import GetDocumentRequest


class GetDocumentSerializer(GetSerializer):
    document_id = serializers.IntegerField()

    def create(self, validated_data) -> GetDocumentRequest:
        return GetDocumentRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='document_id', description='ID of the document',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
