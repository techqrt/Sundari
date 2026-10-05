from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.create_document import CreateDocumentSerializer
from sunndari_apps.artists.serializers.request.get.get_document import GetDocumentSerializer
from sunndari_apps.artists.serializers.request.get.download_document import DownloadDocumentSerializer
from sunndari_apps.artists.serializers.request.delete.delete_document import DeleteDocumentSerializer
from sunndari_apps.artists.serializers.response.get.get_document import DocumentResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_document import DocumentResponseGetAllSerializer
from sunndari_apps.artists.views.document import ArtistDocumentView


class ArtistDocumentController:

    @extend_schema(
        description=(
            'Upload a KYC/verification document (multipart). For document_type=id_proof, id_type '
            '(aadhaar|voter_id|passport|driving_licence) and document_number are required, plus a '
            'back_file for aadhaar, voter_id and driving_licence. A new ID proof replaces the previous one.'
        ),
        request=CreateDocumentSerializer,
        responses=SwaggerPage.response(description='Document uploaded successfully'),
        tags=['Artists - Onboarding'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateDocumentSerializer).validate
    def create_document(request: Request) -> Response:
        return ArtistDocumentView().create_extract(
            params=request.params, file=request.FILES.get('file'), back_file=request.FILES.get('back_file'),
        )

    @extend_schema(
        description='Delete an uploaded document.',
        parameters=DeleteDocumentSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Document deleted successfully'),
        tags=['Artists - Onboarding'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DeleteDocumentSerializer).validate
    def delete_document(request: Request) -> Response:
        return ArtistDocumentView().delete_extract(params=request.params)

    @extend_schema(
        description='Get a single uploaded document.',
        parameters=GetDocumentSerializer.get_parameters(),
        responses=SwaggerPage.response(response=DocumentResponseSerializer),
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetDocumentSerializer).validate
    def get_document(request: Request) -> Response:
        return ArtistDocumentView().get_extract(params=request.params)

    @extend_schema(
        description='Get all uploaded documents for own artist profile.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=DocumentResponseGetAllSerializer),
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_documents(request: Request) -> Response:
        return ArtistDocumentView().get_all_extract(params=request.params)

    @extend_schema(
        description='Download a stored document file. Owner or admin only; never reachable via /media/.',
        parameters=DownloadDocumentSerializer.get_parameters(),
        responses={(200, 'application/octet-stream'): bytes},
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DownloadDocumentSerializer).validate
    def download_document(request: Request) -> Response:
        return ArtistDocumentView().download_extract(params=request.params)
