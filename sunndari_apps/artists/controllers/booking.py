from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.get.get_booking import GetArtistBookingSerializer
from sunndari_apps.artists.serializers.request.update.update_booking_status import UpdateBookingStatusSerializer
from sunndari_apps.customers.serializers.response.get.get_booking import BookingResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_booking import BookingResponseGetAllSerializer
from sunndari_apps.artists.views.booking import ArtistBookingView


class ArtistBookingController:

    @extend_schema(
        description='Get a single booking belonging to own artist profile.',
        parameters=GetArtistBookingSerializer.get_parameters(),
        responses=SwaggerPage.response(response=BookingResponseSerializer),
        tags=['Artists - Bookings'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetArtistBookingSerializer).validate
    def get_booking(request: Request) -> Response:
        return ArtistBookingView().get_extract(params=request.params)

    @extend_schema(
        description='List all bookings for own artist profile.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=BookingResponseGetAllSerializer),
        tags=['Artists - Bookings'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_bookings(request: Request) -> Response:
        return ArtistBookingView().get_all_extract(params=request.params)

    @extend_schema(
        description=(
            "Transition a booking's status. Valid moves: pending→confirmed/cancelled, "
            "confirmed→in_progress/cancelled, in_progress→completed/no_show."
        ),
        request=UpdateBookingStatusSerializer,
        responses=SwaggerPage.response(description='Booking status updated successfully'),
        tags=['Artists - Bookings'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateBookingStatusSerializer).validate
    def update_booking_status(request: Request) -> Response:
        return ArtistBookingView().update_status_extract(params=request.params)
