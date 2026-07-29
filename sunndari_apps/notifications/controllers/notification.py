from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.notifications.serializers.request.get.get_notification import GetNotificationSerializer
from sunndari_apps.notifications.serializers.request.update.mark_read import MarkReadSerializer
from sunndari_apps.notifications.serializers.request.update.mark_all_read import MarkAllReadSerializer
from sunndari_apps.notifications.serializers.response.get.get_notification import NotificationResponseSerializer
from sunndari_apps.notifications.serializers.response.get_all.get_all_notification import NotificationResponseGetAllSerializer
from sunndari_apps.notifications.views.notification import NotificationView


class NotificationController:

    @extend_schema(
        description='Get a single notification belonging to the logged-in user.',
        parameters=GetNotificationSerializer.get_parameters(),
        responses=SwaggerPage.response(response=NotificationResponseSerializer),
        tags=['Notifications'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetNotificationSerializer).validate
    def get_notification(request: Request) -> Response:
        return NotificationView().get_extract(params=request.params)

    @extend_schema(
        description='List all notifications for the logged-in user.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=NotificationResponseGetAllSerializer),
        tags=['Notifications'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_notifications(request: Request) -> Response:
        return NotificationView().get_all_extract(params=request.params)

    @extend_schema(
        description='Mark a single notification as read.',
        request=MarkReadSerializer,
        responses=SwaggerPage.response(description='Notification marked as read'),
        tags=['Notifications'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=MarkReadSerializer).validate
    def mark_read(request: Request) -> Response:
        return NotificationView().mark_read_extract(params=request.params)

    @extend_schema(
        description='Mark all of the logged-in user\'s notifications as read.',
        request=MarkAllReadSerializer,
        responses=SwaggerPage.response(description='All notifications marked as read'),
        tags=['Notifications'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=MarkAllReadSerializer).validate
    def mark_all_read(request: Request) -> Response:
        return NotificationView().mark_all_read_extract(params=request.params)
