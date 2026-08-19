from datetime import datetime, time
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.help_center.dataclasses.request.get.get_admin_messages import AdminGetMessagesRequest


class AdminGetMessagesSerializer(GetAllSerializer):
    conversation_id = serializers.IntegerField()

    def create(self, validated_data) -> AdminGetMessagesRequest:
        from_date = validated_data.get('from_date', None)
        to_date = validated_data.get('to_date', None)
        if from_date:
            validated_data['from_date'] = timezone.make_aware(
                value=datetime.combine(date=from_date, time=time.min)
            )
        if to_date:
            validated_data['to_date'] = timezone.make_aware(
                value=datetime.combine(date=to_date, time=time.max)
            )
        return AdminGetMessagesRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_all_parameters()
        params.append(OpenApiParameter(
            name='conversation_id', description='ID of the support conversation',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
