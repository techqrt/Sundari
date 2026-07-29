from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.notifications.dataclasses.request.get.get_notification import GetNotificationRequest


class GetNotificationSerializer(GetSerializer):
    notification_id = serializers.IntegerField()

    def create(self, validated_data) -> GetNotificationRequest:
        return GetNotificationRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='notification_id', description='ID of the notification',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
