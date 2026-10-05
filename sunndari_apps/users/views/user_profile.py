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
            caller = User.get(user_id=params.user_id)
            is_self = user_data['user_id'] == params.user_id
            is_admin = bool(caller) and caller['role'] == 'admin'
            # Credentials never leave the server through this endpoint (not even for the owner,
            # who already holds the token) and the device token is the owner's alone.
            user_data = {k: v for k, v in user_data.items() if k != 'access_token'}
            if not is_self:
                user_data.pop('fcm_token', None)
                if not is_admin:
                    # Another user: only what is needed to label them. No contact details.
                    user_data = {k: user_data[k] for k in ('user_id', 'name', 'role')}
            utils = UsersUtils(entity='profile', columns_required=[c for c in params.values.split(',') if c])
            data = json.loads(utils.mapper([user_data]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def update_extract(self, params: UserProfileUpdateRequest):
        with transaction.atomic():
            current = User.get(user_id=params.user_id)
            if not current:
                raise ValueError(self.data_no_match)
            # An email/phone is a login identifier and a recovery channel: it can only be
            # changed by proving ownership of the new one (users/contact/change/*), never by
            # a plain profile edit. Re-sending the current value is harmless and allowed.
            if (params.email and params.email != current['email']) or (
                params.phone_number and params.phone_number != current['phone_number']
            ):
                raise ValueError(Constants.contact_change_requires_otp)
            User.update(
                user_id=params.user_id,
                name=params.name,
                fcm_token=params.fcm_token,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.update_msg)
        )
