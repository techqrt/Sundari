from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.admin_panel.serializers.request.get.get_artist_documents import GetArtistDocumentsSerializer
from sunndari_apps.admin_panel.serializers.request.update.verify_document import VerifyDocumentSerializer
from sunndari_apps.admin_panel.serializers.response.get_all.get_all_artist_document import (
    AdminArtistDocumentResponseSerializer,
)
from sunndari_apps.admin_panel.views.artist_document import AdminArtistDocumentView


class AdminArtistDocumentController:

    @extend_schema(
        description=(
            "List an artist's KYC documents for review, including the full ID number. Admin only. "
            'Files are fetched from /artists/documents/file/ (admins are allowed there).'
        ),
        parameters=GetArtistDocumentsSerializer.get_parameters(),
        responses=SwaggerPage.response(response=AdminArtistDocumentResponseSerializer),
        tags=['Admin - Artist Review'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetArtistDocumentsSerializer).validate
    def get_all_documents(request: Request) -> Response:
        return AdminArtistDocumentView().get_all_extract(params=request.params)

    @extend_schema(
        description='Approve or reject a pending KYC document (reason required to reject). Admin only.',
        request=VerifyDocumentSerializer,
        responses=SwaggerPage.response(description='Document decision recorded'),
        tags=['Admin - Artist Review'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyDocumentSerializer).validate
    def verify_document(request: Request) -> Response:
        return AdminArtistDocumentView().verify_extract(params=request.params)
