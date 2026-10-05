from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.brand_requests import ArtistBrandRequestSerializer
from sunndari_apps.artists.views.brand_request import ArtistBrandRequestView


class ArtistBrandRequestController:

    @extend_schema(description='Ask admins to add a brand that is missing from the list (max 5 pending).',
                   request=ArtistBrandRequestSerializer,
                   responses=SwaggerPage.response(description='Brand request submitted'), tags=['Artists - Brands'])
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ArtistBrandRequestSerializer).validate
    def request_brand(request: Request) -> Response:
        return ArtistBrandRequestView().create_extract(params=request.params)

    @extend_schema(description='Your brand requests with their status, newest first.',
                   parameters=SwaggerPage.get_all_parameters(),
                   responses=SwaggerPage.response(description='Brand requests'), tags=['Artists - Brands'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_brand_requests(request: Request) -> Response:
        return ArtistBrandRequestView().get_all_extract(params=request.params)
