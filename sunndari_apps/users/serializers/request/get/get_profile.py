from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.users.dataclasses.request.get.get_profile import UserProfileGetRequest


class UserProfileGetSerializer(GetSerializer):
    user_id = serializers.IntegerField()

    def create(self, validated_data) -> UserProfileGetRequest:
        return UserProfileGetRequest(
            profile_user_id=validated_data['user_id'],
            values=validated_data.get('values', ''),
        )

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='user_id', description='ID of the user whose profile to fetch',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name='values', description='Comma-separated column names to return',
                required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY
            ),
        ]
