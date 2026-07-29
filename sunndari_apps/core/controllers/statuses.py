from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.core.serializers.request.get.get_no_param import NoParamSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_statuses import StatusListResponseSerializer
from sunndari_apps.core.views.statuses import StatusesView


class StatusesController:

    @extend_schema(
        description='Get all booking status values.',
        responses=SwaggerPage.response(response=StatusListResponseSerializer),
        tags=['Core - Statuses'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=NoParamSerializer).validate
    def get_booking_statuses(request: Request) -> Response:
        return StatusesView().get_booking_statuses(params=request.params)

    @extend_schema(
        description='Get all payment status values.',
        responses=SwaggerPage.response(response=StatusListResponseSerializer),
        tags=['Core - Statuses'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=NoParamSerializer).validate
    def get_payment_statuses(request: Request) -> Response:
        return StatusesView().get_payment_statuses(params=request.params)

    @extend_schema(
        description='Get all artist approval status values.',
        responses=SwaggerPage.response(response=StatusListResponseSerializer),
        tags=['Core - Statuses'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=NoParamSerializer).validate
    def get_approval_statuses(request: Request) -> Response:
        return StatusesView().get_approval_statuses(params=request.params)
