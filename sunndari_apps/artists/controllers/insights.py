from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.views.insights import ArtistInsightsView


class ArtistInsightsController:

    @extend_schema(
        description='Your business summary: bookings by status, repeat clients, most-booked services and profile views. Optional from_date/to_date (dd-mm-yy) on the booking date. Earnings are not included yet.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Insights'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_summary(request: Request) -> Response:
        return ArtistInsightsView().summary_extract(params=request.params)
