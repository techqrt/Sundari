from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.salon_address import ArtistSalonAddress
from sunndari.constants import Constants


class SalonAddressView:
    """An artist's salon / studio addresses. Every call works on the caller's own profile: there is no artist id in
    a request, so one artist can never add to, or reach, another's list."""

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def get_all_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message='Data fetched successfully', data=ArtistSalonAddress.get_all_active(profile.artist_id),
            )
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            # Same lock as adding, so a rename cannot race another rename or add into a duplicate name.
            ArtistProfile.objects.select_for_update().filter(artist_id=profile.artist_id).first()
            address = ArtistSalonAddress.get_active_owned(profile.artist_id, params.salon_address_id)
            if not address:
                raise ValueError(Constants.salon_address_not_found)
            changes = {field: getattr(params, field) for field in params.provided}
            if 'name' in changes and ArtistSalonAddress.name_exists(
                profile.artist_id, changes['name'], exclude_salon_address_id=address.salon_address_id,
            ):
                raise ValueError(Constants.salon_address_exists)
            # A move on one axis must not land the pair on 0, 0 (the unset map position) either.
            latitude = changes.get('latitude', address.latitude)
            longitude = changes.get('longitude', address.longitude)
            if latitude == 0 and longitude == 0:
                raise ValueError(Constants.salon_coordinates_unset)
            address.update_fields(**changes)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Salon address updated successfully')
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            ArtistProfile.objects.select_for_update().filter(artist_id=profile.artist_id).first()
            address = ArtistSalonAddress.get_active_owned(profile.artist_id, params.salon_address_id)
            if not address:
                raise ValueError(Constants.salon_address_not_found)
            address.deactivate()
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Salon address deleted successfully')
        )

    @Common().exception_handler
    def create_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            # Serialise two simultaneous adds by the same artist so the limit and the name rule see each other.
            ArtistProfile.objects.select_for_update().filter(artist_id=profile.artist_id).first()
            if ArtistSalonAddress.active_count(profile.artist_id) >= ArtistSalonAddress.MAX_ACTIVE_PER_ARTIST:
                raise ValueError(Constants.salon_address_limit.format(limit=ArtistSalonAddress.MAX_ACTIVE_PER_ARTIST))
            if ArtistSalonAddress.name_exists(profile.artist_id, params.name):
                raise ValueError(Constants.salon_address_exists)
            salon_address_id = ArtistSalonAddress().create(
                artist_id=profile.artist_id, name=params.name, address_line_1=params.address_line_1,
                address_line_2=params.address_line_2, city=params.city, pin_code=params.pin_code,
                latitude=params.latitude, longitude=params.longitude,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Salon address added successfully', data={'salon_address_id': salon_address_id},
            )
        )
