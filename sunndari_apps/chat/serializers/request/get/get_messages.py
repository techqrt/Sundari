from datetime import datetime, time
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.chat.dataclasses.request.get.get_messages import GetMessagesRequest


class GetMessagesSerializer(GetAllSerializer):
    booking_id = serializers.IntegerField()

    def create(self, validated_data) -> GetMessagesRequest:
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
        return GetMessagesRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_all_parameters()
        params.append(OpenApiParameter(
            name='booking_id', description='ID of the booking',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
