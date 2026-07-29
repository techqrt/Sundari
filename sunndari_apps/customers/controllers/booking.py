from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.customers.serializers.request.get.get_booking import GetBookingSerializer
from sunndari_apps.customers.serializers.request.update.cancel_booking import CancelBookingSerializer
from sunndari_apps.customers.serializers.response.get.get_booking import BookingResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_booking import BookingResponseGetAllSerializer
from sunndari_apps.customers.views.booking import BookingView


class BookingController:

    @extend_schema(
        description='Get a single booking belonging to the logged-in customer.',
        parameters=GetBookingSerializer.get_parameters(),
        responses=SwaggerPage.response(response=BookingResponseSerializer),
        tags=['Customers - Booking'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetBookingSerializer).validate
    def get_booking(request: Request) -> Response:
        return BookingView().get_extract(params=request.params)

    @extend_schema(
        description='List all bookings for the logged-in customer.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=BookingResponseGetAllSerializer),
        tags=['Customers - Booking'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_bookings(request: Request) -> Response:
        return BookingView().get_all_extract(params=request.params)

    @extend_schema(
        description='Cancel a booking that is still pending, confirmed, or in progress.',
        request=CancelBookingSerializer,
        responses=SwaggerPage.response(description='Booking cancelled successfully'),
        tags=['Customers - Booking'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CancelBookingSerializer).validate
    def cancel_booking(request: Request) -> Response:
        return BookingView().cancel_extract(params=request.params)
