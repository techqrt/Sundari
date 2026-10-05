import json
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.service_area import ArtistServiceArea
from sunndari_apps.artists.serializers.response.get_all.get_all_service_area import ServiceAreaResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class ServiceAreaView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def add_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            if ArtistServiceArea.city_exists(profile.artist_id, params.city):
                raise ValueError(Constants.service_area_exists)
            area_id = ArtistServiceArea().create(
                artist_id=profile.artist_id, city=params.city, travel_charge_type=params.travel_charge_type,
                charge_amount=params.charge_amount or 0,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Service area added successfully', data={'area_id': area_id})
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            area = ArtistServiceArea.get(area_id=params.area_id)
            if not area or area['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            if params.city and ArtistServiceArea.city_exists(profile.artist_id, params.city, exclude_area_id=params.area_id):
                raise ValueError(Constants.service_area_exists)
            # The final charge type/amount pair must stay consistent, whichever half was sent.
            charge_type = params.travel_charge_type or area['travel_charge_type']
            charge_amount = params.charge_amount if params.charge_amount is not None else area['charge_amount']
            if charge_type == 'free':
                charge_amount = 0
            elif not charge_amount:
                raise ValueError('charge_amount is required for a per-visit charge')
            ArtistServiceArea.update(
                area_id=params.area_id, city=params.city, travel_charge_type=charge_type,
                charge_amount=charge_amount, is_active=params.is_active,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Service area updated successfully')
        )

    @Common().exception_handler
    def remove_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            area = ArtistServiceArea.get(area_id=params.area_id)
            if not area or area['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            ArtistServiceArea.remove(area_id=params.area_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Service area removed successfully')
        )

    @Common(response_handler=ServiceAreaResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params):
        own = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if params.artist_id and (not own or own.artist_id != params.artist_id):
            target = ArtistProfile.objects.filter(artist_id=params.artist_id, approval_status__name='approved').first()
            if not target:
                raise ValueError(Constants.artist_not_found)
            profile, only_active = target, True
        else:
            profile, only_active = self._get_profile(user_id=params.user_id), False
        rows = ArtistServiceArea.get_all(artist_id=profile.artist_id, only_active=only_active)
        data = json.loads(ArtistsUtils(entity='service_area').mapper(rows))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
