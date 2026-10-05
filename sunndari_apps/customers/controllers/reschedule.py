from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.customers.serializers.request.update.respond_reschedule import RespondRescheduleSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_reschedule import RescheduleResponseGetAllSerializer
from sunndari_apps.customers.views.reschedule import CustomerRescheduleView


class RescheduleController:

    @extend_schema(
        description=(
            'Accept or reject an artist\'s reschedule request for one of your bookings. Accepting moves the '
            'booking (the slot is re-checked at that moment); rejecting leaves it unchanged. A request that '
            'is no longer pending cannot be answered again.'
        ),
        request=RespondRescheduleSerializer,
        responses=SwaggerPage.response(description='Reschedule decision recorded'),
        tags=['Customers - Reschedule'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RespondRescheduleSerializer).validate
    def respond_reschedule(request: Request) -> Response:
        return CustomerRescheduleView().respond_extract(params=request.params)

    @extend_schema(
        description=(
            'Reschedule requests on your bookings, newest first. Narrow to one booking with '
            'filter_key=bookingId&filter_value=<id>.'
        ),
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=RescheduleResponseGetAllSerializer),
        tags=['Customers - Reschedule'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_reschedules(request: Request) -> Response:
        return CustomerRescheduleView().get_all_extract(params=request.params)
