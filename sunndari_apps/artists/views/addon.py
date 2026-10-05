import json
from django.db import transaction
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.addon import PackageAddOn
from sunndari_apps.artists.serializers.response.get.get_addon import AddOnResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_addon import AddOnResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class AddOnView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    def _check_packages_belong_to_artist(self, artist_id: int, package_ids: list) -> list:
        unique_ids = sorted(set(package_ids or []))
        owned = PricingPackage.objects.filter(artist_id=artist_id, package_id__in=unique_ids).count()
        if owned != len(unique_ids):
            raise ValueError(self.data_no_match)
        return unique_ids

    def _own_addon(self, artist_id: int, addon_id: int) -> dict:
        addon = PackageAddOn.get(addon_id=addon_id)
        if not addon or addon['artist_id'] != artist_id:
            raise ValueError(self.data_no_match)
        return addon

    @Common().exception_handler
    def create_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            package_ids = self._check_packages_belong_to_artist(profile.artist_id, params.package_ids)
            addon_id = PackageAddOn().create(
                artist_id=profile.artist_id, name=params.name, price=params.price,
                duration_minutes=params.duration_minutes, description=params.description,
                is_active=params.is_active, package_ids=package_ids,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Add-on created successfully', data={'addon_id': addon_id})
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            self._own_addon(profile.artist_id, params.addon_id)
            package_ids = None
            if params.package_ids is not None:
                package_ids = self._check_packages_belong_to_artist(profile.artist_id, params.package_ids)
            PackageAddOn.update(
                addon_id=params.addon_id, name=params.name, price=params.price,
                duration_minutes=params.duration_minutes, description=params.description,
                is_active=params.is_active, package_ids=package_ids,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Add-on updated successfully')
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            self._own_addon(profile.artist_id, params.addon_id)
            PackageAddOn.remove(addon_id=params.addon_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Add-on deleted successfully')
        )

    @Common(response_handler=AddOnResponseSerializer).exception_handler
    def get_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        addon = self._own_addon(profile.artist_id, params.addon_id)
        columns = [c for c in params.values.split(',') if c]
        mapped = ArtistsUtils.map_addons([addon])[0]
        unknown = [column for column in columns if column not in mapped]
        if unknown:
            raise ValueError(f'{unknown[0]} not a proper column name')
        data = {key: mapped[key] for key in columns} if columns else mapped
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=AddOnResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        own = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if params.artist_id and (not own or own.artist_id != params.artist_id):
            # Someone else's add-ons: only the active ones of an approved artist.
            target = ArtistProfile.objects.filter(artist_id=params.artist_id, approval_status__name='approved').first()
            if not target:
                raise ValueError(Constants.artist_not_found)
            profile, only_active = target, True
        else:
            profile, only_active = self._get_profile(user_id=params.user_id), False
        reversed_mapped = ArtistsUtils.reverse_mapper('addon', [params.sort_by, params.filter_key])
        pages = Paginator(
            PackageAddOn.get_all(
                artist_id=profile.artist_id,
                only_active=only_active,
                sort_by=reversed_mapped.get(params.sort_by, ''),
                sort_order=params.sort_order,
                filter_key=reversed_mapped.get(params.filter_key, ''),
                filter_value=params.filter_value,
                search_key=params.search_key,
            ),
            per_page=params.limit
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        data = ArtistsUtils.map_addons(list(pages.page(params.page_num)))
        data = Utils.add_page_parameter(
            final_data=data,
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
