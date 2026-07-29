from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.get.check_availability import CheckAvailabilitySerializer
from sunndari_apps.customers.serializers.response.get.check_availability import AvailabilityResponseSerializer
from sunndari_apps.customers.views.check_availability import CheckAvailabilityView


class CheckAvailabilityController:

    @extend_schema(
        description=(
            "Check an artist's working window, blocked-day status, and already-booked "
            "time ranges for a given date."
        ),
        parameters=CheckAvailabilitySerializer.get_parameters(),
        responses=SwaggerPage.response(response=AvailabilityResponseSerializer),
        tags=['Customers - Booking'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CheckAvailabilitySerializer).validate
    def check_availability(request: Request) -> Response:
        return CheckAvailabilityView().get_extract(params=request.params)
