from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.create.create_booking import CreateBookingSerializer
from sunndari_apps.customers.views.create_booking import CreateBookingView


class CreateBookingController:

    @extend_schema(
        description=(
            'Create a booking request for an artist package. Slot is locked for 15 minutes '
            'pending payment; still-pending bookings auto-cancel after that.'
        ),
        request=CreateBookingSerializer,
        responses=SwaggerPage.response(description='Slot locked for 15 minutes pending payment'),
        tags=['Customers - Booking'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateBookingSerializer).validate
    def create_booking(request: Request) -> Response:
        return CreateBookingView().create_extract(params=request.params)
