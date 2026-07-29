from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.get.search_artist import SearchArtistSerializer
from sunndari_apps.customers.serializers.response.get_all.search_artist import ArtistSearchResponseGetAllSerializer
from sunndari_apps.customers.views.search_artist import SearchArtistView


class SearchArtistController:

    @extend_schema(
        description=(
            'Search approved, publicly visible artists (≥1 active package). '
            'Filter by city, category/sub-category, price range, and minimum rating.'
        ),
        parameters=SearchArtistSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ArtistSearchResponseGetAllSerializer),
        tags=['Customers - Search'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SearchArtistSerializer).validate
    def search_artists(request: Request) -> Response:
        return SearchArtistView().search_extract(params=request.params)
