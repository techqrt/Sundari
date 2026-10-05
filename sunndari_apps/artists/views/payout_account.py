import json
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.payout_account import ArtistPayoutAccount
from sunndari_apps.artists.serializers.response.get.get_payout_account import PayoutAccountResponseSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


def _mask_account_number(bank_account_number: str) -> str:
    if not bank_account_number or len(bank_account_number) <= 4:
        return 'XXXX'
    return 'X' * (len(bank_account_number) - 4) + bank_account_number[-4:]


class ArtistPayoutAccountView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def set_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            ArtistPayoutAccount.set_for_artist(
                artist_id=profile.artist_id,
                account_holder_name=params.account_holder_name,
                bank_account_number=params.bank_account_number,
                ifsc_code=params.ifsc_code,
                upi_id=params.upi_id or None,
            )
            # Changing where money goes is security-sensitive: tell the account owner (the
            # new account is also back to 'pending' verification — see set_for_artist).
            NotificationService.notify(
                user_id=params.user_id, title='Payout account updated',
                message='Your payout bank account was changed. If this was not you, contact support.',
                type='payout_account_changed',
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Payout account saved successfully')
        )

    @Common(response_handler=PayoutAccountResponseSerializer).exception_handler
    def get_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        item = ArtistPayoutAccount.get(artist_id=profile.artist_id)
        if not item:
            raise ValueError(self.data_no_match)
        # bank_account_number never leaves the backend raw — masked before it ever reaches the mapper
        safe_item = {k: v for k, v in item.items() if k != 'bank_account_number'}
        safe_item['bank_account_number_masked'] = _mask_account_number(item['bank_account_number'])
        utils = ArtistsUtils(entity='payout_account', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([safe_item]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
