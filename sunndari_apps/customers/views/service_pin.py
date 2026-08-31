from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.dataclasses.request.get.get_start_pin import GetStartPinRequest
from sunndari_apps.customers.dataclasses.request.get.get_completion_pin import GetCompletionPinRequest
from sunndari_apps.customers.serializers.response.get.service_pin import (
    StartPinResponseSerializer, CompletionPinResponseSerializer,
)
from sunndari.constants import Constants


class StartPinView:

    @Common(response_handler=StartPinResponseSerializer).exception_handler
    def get_extract(self, params: GetStartPinRequest):
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)
        if booking['start_service_pin'] is None:
            raise ValueError(Constants.start_pin_not_available)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message=Constants.data_get,
                data={'bookingId': booking['booking_id'], 'startServicePin': booking['start_service_pin']},
            )
        )


class CompletionPinView:

    @Common(response_handler=CompletionPinResponseSerializer).exception_handler
    def get_extract(self, params: GetCompletionPinRequest):
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)
        if booking['completion_pin'] is None:
            raise ValueError(Constants.completion_pin_not_available)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message=Constants.data_get,
                data={'bookingId': booking['booking_id'], 'completionPin': booking['completion_pin']},
            )
        )
