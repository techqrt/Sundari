from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.set_schedule import SetScheduleSerializer
from sunndari_apps.artists.serializers.request.delete.remove_schedule import RemoveScheduleSerializer
from sunndari_apps.artists.serializers.request.create.add_block import AddBlockSerializer
from sunndari_apps.artists.serializers.request.delete.remove_block import RemoveBlockSerializer
from sunndari_apps.artists.views.availability import AvailabilityView


class AvailabilityController:

    @extend_schema(
        description='Set or replace a recurring availability slot for a day of the week.',
        request=SetScheduleSerializer,
        responses=SwaggerPage.response(description='Schedule set successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SetScheduleSerializer).validate
    def set_schedule(request: Request) -> Response:
        return AvailabilityView().set_schedule_extract(params=request.params)

    @extend_schema(
        description='Remove recurring availability for a specific day.',
        parameters=RemoveScheduleSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Schedule removed successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RemoveScheduleSerializer).validate
    def remove_schedule(request: Request) -> Response:
        return AvailabilityView().remove_schedule_extract(params=request.params)

    @extend_schema(
        description='Get all recurring availability schedules for own artist profile.',
        responses=SwaggerPage.response(description='Data fetched successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_schedules(request: Request) -> Response:
        return AvailabilityView().get_all_schedules_extract(params=request.params)

    @extend_schema(
        description='Block a specific date (overrides recurring schedule).',
        request=AddBlockSerializer,
        responses=SwaggerPage.response(description='Date blocked successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AddBlockSerializer).validate
    def add_block(request: Request) -> Response:
        return AvailabilityView().add_block_extract(params=request.params)

    @extend_schema(
        description='Unblock a previously blocked date.',
        parameters=RemoveBlockSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Date unblocked successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RemoveBlockSerializer).validate
    def remove_block(request: Request) -> Response:
        return AvailabilityView().remove_block_extract(params=request.params)

    @extend_schema(
        description='Get all blocked dates for own artist profile.',
        responses=SwaggerPage.response(description='Data fetched successfully'),
        tags=['Artists - Availability'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_blocks(request: Request) -> Response:
        return AvailabilityView().get_all_blocks_extract(params=request.params)
