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
from sunndari_apps.artists.serializers.request.update.on_my_way import OnMyWaySerializer
from sunndari_apps.artists.serializers.request.update.arrived import ArrivedSerializer
from sunndari_apps.artists.serializers.request.update.verify_start_pin import VerifyStartPinSerializer
from sunndari_apps.artists.serializers.request.update.verify_completion_pin import VerifyCompletionPinSerializer
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

    @extend_schema(
        description=(
            "Mark a confirmed booking as 'on the way'. Only allowed within 2 hours of the "
            "booking's scheduled start time."
        ),
        request=OnMyWaySerializer,
        responses=SwaggerPage.response(description='Marked as on the way'),
        tags=['Artists - Bookings'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=OnMyWaySerializer).validate
    def on_my_way(request: Request) -> Response:
        return ArtistBookingView().on_my_way_extract(params=request.params)

    @extend_schema(
        description=(
            "Confirm the artist has arrived. Requires the Booking OTP issued to the artist "
            "at booking creation. On success, generates the Start Service PIN for the customer."
        ),
        request=ArrivedSerializer,
        responses=SwaggerPage.response(description='Arrival confirmed'),
        tags=['Artists - Bookings'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ArrivedSerializer).validate
    def arrived(request: Request) -> Response:
        return ArtistBookingView().arrived_extract(params=request.params)

    @extend_schema(
        description=(
            "Verify the Start Service PIN shown to the customer. On success transitions "
            "the booking to 'in_progress' and generates the Completion PIN."
        ),
        request=VerifyStartPinSerializer,
        responses=SwaggerPage.response(description='Service started'),
        tags=['Artists - Bookings'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyStartPinSerializer).validate
    def verify_start_pin(request: Request) -> Response:
        return ArtistBookingView().verify_start_pin_extract(params=request.params)

    @extend_schema(
        description=(
            "Verify the Completion PIN shown to the customer. On success transitions "
            "the booking to 'completed' and closes the booking's chat conversation."
        ),
        request=VerifyCompletionPinSerializer,
        responses=SwaggerPage.response(description='Service completed'),
        tags=['Artists - Bookings'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyCompletionPinSerializer).validate
    def verify_completion_pin(request: Request) -> Response:
        return ArtistBookingView().verify_completion_pin_extract(params=request.params)
