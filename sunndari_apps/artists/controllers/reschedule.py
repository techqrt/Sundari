from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.request_reschedule import RequestRescheduleSerializer
from sunndari_apps.artists.serializers.request.update.cancel_reschedule import CancelRescheduleSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_reschedule import RescheduleResponseGetAllSerializer
from sunndari_apps.artists.views.reschedule import ArtistRescheduleView


class ArtistRescheduleController:

    @extend_schema(
        description=(
            'Ask the customer to move a confirmed booking to a new date/start time (the booking keeps its '
            'length). The booking only changes if the customer accepts; the request lapses after '
            '24 hours or at the original start time, whichever is earlier. One open request per booking.'
        ),
        request=RequestRescheduleSerializer,
        responses=SwaggerPage.response(description='Reschedule requested'),
        tags=['Artists - Reschedule'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RequestRescheduleSerializer).validate
    def request_reschedule(request: Request) -> Response:
        return ArtistRescheduleView().request_extract(params=request.params)

    @extend_schema(
        description='Withdraw your own pending reschedule request.',
        request=CancelRescheduleSerializer,
        responses=SwaggerPage.response(description='Reschedule request cancelled'),
        tags=['Artists - Reschedule'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CancelRescheduleSerializer).validate
    def cancel_reschedule(request: Request) -> Response:
        return ArtistRescheduleView().cancel_extract(params=request.params)

    @extend_schema(
        description=(
            'Reschedule requests on your bookings, newest first. Narrow to one booking with '
            'filter_key=bookingId&filter_value=<id>.'
        ),
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=RescheduleResponseGetAllSerializer),
        tags=['Artists - Reschedule'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_reschedules(request: Request) -> Response:
        return ArtistRescheduleView().get_all_extract(params=request.params)
