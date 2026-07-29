import json
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.availability_schedule import ArtistAvailabilitySchedule
from sunndari_apps.artists.models.availability_block import ArtistAvailabilityBlock
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class AvailabilityView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def set_schedule_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            obj = ArtistAvailabilitySchedule()
            obj.set(
                artist_id=profile.artist_id,
                day_of_week=params.day_of_week,
                start_time=params.start_time,
                end_time=params.end_time,
                location_type_id=params.location_type_id,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Schedule set successfully')
        )

    @Common().exception_handler
    def remove_schedule_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            ArtistAvailabilitySchedule.remove(
                artist_id=profile.artist_id,
                day_of_week=params.day_of_week,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Schedule removed successfully')
        )

    @Common().exception_handler
    def get_all_schedules_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        raw = ArtistAvailabilitySchedule.get_all(artist_id=profile.artist_id)
        utils = ArtistsUtils(entity='schedule')
        data = json.loads(utils.mapper(raw))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def add_block_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            ArtistAvailabilityBlock.add(
                artist_id=profile.artist_id,
                block_date=params.block_date,
                note=params.note,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Date blocked successfully')
        )

    @Common().exception_handler
    def remove_block_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            ArtistAvailabilityBlock.remove(
                artist_id=profile.artist_id,
                block_date=params.block_date,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Date unblocked successfully')
        )

    @Common().exception_handler
    def get_all_blocks_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        raw = ArtistAvailabilityBlock.get_all(artist_id=profile.artist_id)
        utils = ArtistsUtils(entity='block')
        data = json.loads(utils.mapper(raw))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
