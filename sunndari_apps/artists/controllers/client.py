from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.update.set_client_note import SetClientNoteSerializer
from sunndari_apps.artists.views.client import ArtistClientView


class ArtistClientController:

    @extend_schema(
        description='Your clients (customers with a confirmed, started or completed booking) with your private note. search_key matches the name; sort_by name|lastBookingDate|bookingsCount.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Clients'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_clients(request: Request) -> Response:
        return ArtistClientView().get_all_extract(params=request.params)

    @extend_schema(
        description='Save a private note about a client (blank clears it). Never visible to the client.',
        request=SetClientNoteSerializer,
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Clients'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SetClientNoteSerializer).validate
    def set_client_note(request: Request) -> Response:
        return ArtistClientView().set_note_extract(params=request.params)
