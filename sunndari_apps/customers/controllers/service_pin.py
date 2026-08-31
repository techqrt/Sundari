from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.customers.serializers.request.get.get_start_pin import GetStartPinSerializer
from sunndari_apps.customers.serializers.request.get.get_completion_pin import GetCompletionPinSerializer
from sunndari_apps.customers.serializers.response.get.service_pin import (
    StartPinResponseSerializer, CompletionPinResponseSerializer,
)
from sunndari_apps.customers.views.service_pin import StartPinView, CompletionPinView


class StartPinController:

    @extend_schema(
        description='Get the Start Service PIN for a booking the artist has arrived at. Share this with the artist to begin the service.',
        parameters=GetStartPinSerializer.get_parameters(),
        responses=SwaggerPage.response(response=StartPinResponseSerializer),
        tags=['Customers - Booking'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetStartPinSerializer).validate
    def get_start_pin(request: Request) -> Response:
        return StartPinView().get_extract(params=request.params)


class CompletionPinController:

    @extend_schema(
        description='Get the Completion PIN for a booking whose service is in progress. Share this with the artist once the service is finished.',
        parameters=GetCompletionPinSerializer.get_parameters(),
        responses=SwaggerPage.response(response=CompletionPinResponseSerializer),
        tags=['Customers - Booking'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetCompletionPinSerializer).validate
    def get_completion_pin(request: Request) -> Response:
        return CompletionPinView().get_extract(params=request.params)
