from datetime import datetime, time
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.help_center.models.conversation import SupportConversation
from sunndari_apps.help_center.dataclasses.request.get.get_admin_conversations import AdminGetConversationsRequest


class AdminGetConversationsSerializer(GetAllSerializer):
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in SupportConversation.STATUS_CHOICES], required=False, default='',
    )

    def create(self, validated_data) -> AdminGetConversationsRequest:
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
        return AdminGetConversationsRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_all_parameters()
        params.append(OpenApiParameter(
            name='status', description='Filter by conversation status: open, running or closed',
            required=False, type=str,
        ))
        return params
