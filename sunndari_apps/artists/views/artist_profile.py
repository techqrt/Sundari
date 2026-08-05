import json
from django.db import transaction
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.artist_service_offering import ArtistServiceOffering
from sunndari_apps.artists.models.artist_location_preference import ArtistLocationPreference
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_profile import ArtistProfileResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
from sunndari_apps.core.models.location_type import LocationType
from sunndari.constants import Constants


class ArtistProfileView:
    def __init__(self):
        self.update_msg = 'Profile updated successfully'
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_artist_profile(self, user_id: int):
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common(response_handler=ArtistProfileResponseSerializer).exception_handler
    def get_extract(self, params):
        if params.artist_id:
            data_dict = ArtistProfile.get(artist_id=params.artist_id)
        else:
            data_dict = ArtistProfile.get(user_id=params.user_id)
        if not data_dict:
            raise ValueError(self.data_no_match)
        utils = ArtistsUtils(entity='profile', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([data_dict]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            ArtistProfile.update(
                user_id=params.user_id,
                bio=params.bio,
                years_experience=params.years_experience,
                city=params.city,
                service_radius_km=params.service_radius_km,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.update_msg)
        )

    @Common().exception_handler
    def add_service_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            if not ServiceSubCategory.objects.filter(sub_category_id=params.sub_category_id).exists():
                raise ValueError(self.data_no_match)
            ArtistServiceOffering.add(
                artist_id=ArtistProfile.objects.get(user_id=params.user_id).artist_id,
                sub_category_id=params.sub_category_id,
                custom_price=params.custom_price,
                custom_duration_minutes=params.custom_duration_minutes,
            )
            ArtistProfile.update(user_id=params.user_id, reset_approval=True)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Service offering added successfully')
        )

    @Common().exception_handler
    def remove_service_extract(self, params):
        with transaction.atomic():
            profile = ArtistProfile.objects.get(user_id=params.user_id)
            ArtistServiceOffering.remove(
                artist_id=profile.artist_id,
                sub_category_id=params.sub_category_id,
            )
            ArtistProfile.update(user_id=params.user_id, reset_approval=True)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Service offering removed successfully')
        )

    @Common().exception_handler
    def get_all_services_extract(self, params):
        if params.artist_id:
            profile = ArtistProfile.objects.filter(artist_id=params.artist_id).first()
        else:
            profile = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        raw = ArtistServiceOffering.get_all(artist_id=profile.artist_id)
        utils = ArtistsUtils(entity='service_offering')
        data = json.loads(utils.mapper(raw))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def add_location_extract(self, params):
        with transaction.atomic():
            profile = self._get_artist_profile(user_id=params.user_id)
            if not LocationType.objects.filter(location_type_id=params.location_type_id).exists():
                raise ValueError(self.data_no_match)
            ArtistLocationPreference.add(
                artist_id=profile.artist_id,
                location_type_id=params.location_type_id,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Location preference added successfully')
        )

    @Common().exception_handler
    def remove_location_extract(self, params):
        with transaction.atomic():
            profile = ArtistProfile.objects.get(user_id=params.user_id)
            ArtistLocationPreference.remove(
                artist_id=profile.artist_id,
                location_type_id=params.location_type_id,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Location preference removed successfully')
        )

    @Common().exception_handler
    def get_all_locations_extract(self, params):
        if params.artist_id:
            profile = ArtistProfile.objects.filter(artist_id=params.artist_id).first()
        else:
            profile = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        raw = ArtistLocationPreference.get_all(artist_id=profile.artist_id)
        utils = ArtistsUtils(entity='location_preference')
        data = json.loads(utils.mapper(raw))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
