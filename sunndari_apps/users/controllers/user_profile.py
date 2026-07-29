from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.users.serializers.request.get.get_profile import UserProfileGetSerializer
from sunndari_apps.users.serializers.request.update.update_profile import UserProfileUpdateSerializer
from sunndari_apps.users.serializers.response.get.get_profile import UserProfileResponseGetSerializer
from sunndari_apps.users.views.user_profile import UserProfileView


class UserProfileController:

    @extend_schema(
        description='Get a user profile by user_id.',
        parameters=UserProfileGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=UserProfileResponseGetSerializer),
        tags=['Users - Profile'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UserProfileGetSerializer).validate
    def get_profile(request: Request) -> Response:
        return UserProfileView().get_extract(params=request.params)

    @extend_schema(
        description='Update the logged-in user profile.',
        request=UserProfileUpdateSerializer,
        responses=SwaggerPage.response(description=UserProfileView().update_msg),
        tags=['Users - Profile'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UserProfileUpdateSerializer).validate
    def update_profile(request: Request) -> Response:
        return UserProfileView().update_extract(params=request.params)
