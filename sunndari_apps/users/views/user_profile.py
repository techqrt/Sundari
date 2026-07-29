import json
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.authentication.models import User
from sunndari_apps.users.dataclasses.request.update.update_profile import UserProfileUpdateRequest
from sunndari_apps.users.serializers.response.get.get_profile import UserProfileResponseGetSerializer
from sunndari_apps.users.utils import UsersUtils
from sunndari.constants import Constants


class UserProfileView:
    def __init__(self):
        self.update_msg = 'Profile updated successfully'
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    @Common(response_handler=UserProfileResponseGetSerializer).exception_handler
    def get_extract(self, params):
        with transaction.atomic():
            user_data = User.get(user_id=params.profile_user_id)
            if not user_data:
                raise ValueError(self.data_no_match)
            utils = UsersUtils(entity='profile', columns_required=[c for c in params.values.split(',') if c])
            data = json.loads(utils.mapper([user_data]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def update_extract(self, params: UserProfileUpdateRequest):
        with transaction.atomic():
            if not User.get(user_id=params.user_id):
                raise ValueError(self.data_no_match)
            if params.email and User.objects.filter(email=params.email).exclude(user_id=params.user_id).exists():
                raise ValueError(Constants.email_not_unique)
            if params.phone_number and User.objects.filter(phone_number=params.phone_number).exclude(user_id=params.user_id).exists():
                raise ValueError(Constants.mobile_number_not_unique)
            User.update(
                user_id=params.user_id,
                name=params.name,
                email=params.email,
                phone_number=params.phone_number,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.update_msg)
        )
