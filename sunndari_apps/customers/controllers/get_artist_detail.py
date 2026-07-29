from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.get.get_artist_detail import ArtistDetailSerializer
from sunndari_apps.customers.serializers.response.get.get_artist_detail import ArtistDetailResponseSerializer
from sunndari_apps.customers.views.get_artist_detail import ArtistDetailView


class ArtistDetailController:

    @extend_schema(
        description=(
            'Get full artist detail for customer view: profile, active packages, '
            'active portfolio items, and active service offerings in one response. '
            'Only approved artists are visible.'
        ),
        parameters=ArtistDetailSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ArtistDetailResponseSerializer),
        tags=['Customers - Artists'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ArtistDetailSerializer).validate
    def get_artist_detail(request: Request) -> Response:
        return ArtistDetailView().get_extract(params=request.params)
