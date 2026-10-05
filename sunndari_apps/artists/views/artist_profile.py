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
from sunndari_apps.artists.models.artist_speciality import ArtistSpeciality
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_profile import ArtistProfileResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from urllib.parse import urlsplit

from sunndari_apps.common.uploads import validate_image, absolute_file_url
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
from sunndari_apps.core.models.location_type import LocationType
from sunndari_apps.users.models.customer_address import CustomerAddress
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

    # What any other authenticated user may see of an artist. Internal fields
    # (commission rate, review/approval state, agreement, rejection reason, base address)
    # are only ever returned to the artist themselves.
    PUBLIC_PROFILE_FIELDS = (
        'artist_id', 'user_id', 'display_name', 'instagram_url', 'profile_type', 'profile_photo',
        'cover_photo', 'is_accepting_bookings', 'bio', 'years_experience', 'city', 'service_radius_km', 'avg_rating', 'total_reviews', 'created_at', 'updated_at',
    )

    @staticmethod
    def _photo_urls(row: dict, present_url: str) -> dict:
        """Stored file names -> absolute URLs (None when unset), so clients get something
        they can load directly. The host comes from the URL of the request itself."""
        for field in ('profile_photo', 'cover_photo'):
            if field in row:
                row[field] = absolute_file_url(ArtistProfile._meta.get_field(field), row[field], present_url)
        return row

    @Common(response_handler=ArtistProfileResponseSerializer).exception_handler
    def get_extract(self, params):
        own = ArtistProfile.get(user_id=params.user_id)
        is_foreign = bool(params.artist_id) and (not own or own['artist_id'] != params.artist_id)
        columns = [c for c in params.values.split(',') if c]
        if is_foreign:
            data_dict = ArtistProfile.objects.filter(
                artist_id=params.artist_id, approval_status__name='approved',
            ).values(*self.PUBLIC_PROFILE_FIELDS).first()
            public_names = {
                ArtistsUtils.MAPS['profile'][field] for field in self.PUBLIC_PROFILE_FIELDS
            }
            # 'specialities' is a derived public field, not a column of the mapper.
            if any(column not in public_names | {'specialities'} for column in columns):
                raise ValueError(Constants.data_no_match)
        else:
            data_dict = own
        if not data_dict:
            raise ValueError(self.data_no_match)
        data_dict = self._photo_urls(dict(data_dict), params.present_url)
        mapped_columns = [column for column in columns if column != 'specialities']
        utils = ArtistsUtils(entity='profile', columns_required=mapped_columns)
        data = json.loads(utils.mapper([data_dict]))[0]
        if not columns or 'specialities' in columns:
            data['specialities'] = [
                row['sub_category_id'] for row in ArtistSpeciality.get_all(artist_id=data_dict['artist_id'])
            ]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            if params.base_address_id is not None:
                address = CustomerAddress.get(address_id=params.base_address_id)
                if not address or address['user_id'] != params.user_id:
                    raise ValueError(self.data_no_match)
            ArtistProfile.update(
                user_id=params.user_id,
                display_name=params.display_name,
                travel_time_before_minutes=params.travel_time_before_minutes,
                return_buffer_minutes=params.return_buffer_minutes,
                date_of_birth=params.date_of_birth,
                instagram_url=params.instagram_url,
                profile_type=params.profile_type,
                bio=params.bio,
                years_experience=params.years_experience,
                city=params.city,
                service_radius_km=params.service_radius_km,
                base_address_id=params.base_address_id,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.update_msg)
        )

    @Common().exception_handler
    def accept_agreement_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            ArtistProfile.accept_agreement(user_id=params.user_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Partner agreement accepted')
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

    @Common().exception_handler
    def set_specialities_extract(self, params):
        with transaction.atomic():
            profile = self._get_artist_profile(user_id=params.user_id)
            wanted = set(params.sub_category_ids)
            offered = set(
                ArtistServiceOffering.objects.filter(artist_id=profile.artist_id).values_list('sub_category_id', flat=True)
            )
            if not wanted <= offered:
                raise ValueError(Constants.speciality_not_offered)
            ArtistSpeciality.replace_for_artist(artist_id=profile.artist_id, sub_category_ids=list(wanted))
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Specialities updated successfully')
        )

    @Common().exception_handler
    def get_all_specialities_extract(self, params):
        if params.artist_id:
            profile = ArtistProfile.objects.filter(artist_id=params.artist_id).first()
        else:
            profile = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        data = [
            {'subCategoryId': row['sub_category_id'], 'name': row['sub_category__name']}
            for row in ArtistSpeciality.get_all(artist_id=profile.artist_id)
        ]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def upload_photos_extract(self, params, profile_photo=None, cover_photo=None):
        if not profile_photo and not cover_photo:
            raise ValueError(Constants.photo_required)
        for upload in (profile_photo, cover_photo):
            if upload:
                validate_image(upload)
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            ArtistProfile.set_photos(
                user_id=params.user_id, profile_photo=profile_photo, cover_photo=cover_photo,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Photos uploaded successfully')
        )

    @Common().exception_handler
    def delete_photo_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            if not ArtistProfile.remove_photo(user_id=params.user_id, kind=params.kind):
                raise ValueError(self.data_no_match)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Photo removed successfully')
        )

    @Common().exception_handler
    def set_accepting_bookings_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            ArtistProfile.set_accepting_bookings(user_id=params.user_id, accepting=params.is_accepting_bookings)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message='Bookings are now ' + ('on' if params.is_accepting_bookings else 'off'),
                data={'isAcceptingBookings': params.is_accepting_bookings},
            )
        )

    @Common().exception_handler
    def get_share_link_extract(self, params):
        with transaction.atomic():
            self._get_artist_profile(user_id=params.user_id)
            slug = ArtistProfile.ensure_public_slug(user_id=params.user_id)
        parts = urlsplit(params.present_url or '')
        origin = f'{parts.scheme}://{parts.netloc}' if parts.netloc else ''
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message=self.data_get,
                data={'slug': slug, 'url': f'{origin}/public/artists/get/?slug={slug}'},
            )
        )
