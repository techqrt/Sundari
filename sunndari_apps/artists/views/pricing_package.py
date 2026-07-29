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
from sunndari_apps.artists.models.package_inclusion import PackageInclusion
from sunndari_apps.artists.serializers.response.get.get_package import PackageResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_package import PackageResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class PricingPackageView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_profile(self, user_id: int, artist_id: int = None) -> ArtistProfile:
        if artist_id:
            profile = ArtistProfile.objects.filter(artist_id=artist_id).first()
        else:
            profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    def _build_package_response(self, package_dict: dict) -> dict:
        utils = ArtistsUtils(entity='package')
        pkg = json.loads(utils.mapper([package_dict]))[0]
        inclusions_raw = PackageInclusion.get_for_package(package_id=package_dict['package_id'])
        inc_utils = ArtistsUtils(entity='inclusion')
        pkg['inclusions'] = json.loads(inc_utils.mapper(inclusions_raw))
        return pkg

    @Common().exception_handler
    def create_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            obj = PricingPackage()
            package_id = obj.create(
                artist_id=profile.artist_id,
                sub_category_id=params.sub_category_id,
                name=params.name,
                price=params.price,
                duration_minutes=params.duration_minutes,
                description=params.description,
            )
            if params.inclusions:
                PackageInclusion.set_for_package(package_id=package_id, inclusions=params.inclusions)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Package created successfully', data={'package_id': package_id})
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            pkg = PricingPackage.get(package_id=params.package_id)
            if not pkg or pkg['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            PricingPackage.update(
                package_id=params.package_id,
                name=params.name,
                price=params.price,
                duration_minutes=params.duration_minutes,
                description=params.description,
                sub_category_id=params.sub_category_id,
                is_active=params.is_active,
            )
            if params.inclusions is not None:
                PackageInclusion.set_for_package(package_id=params.package_id, inclusions=params.inclusions)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Package updated successfully')
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            pkg = PricingPackage.get(package_id=params.package_id)
            if not pkg or pkg['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            if pkg['is_active'] and PricingPackage.active_count(artist_id=profile.artist_id) <= 1:
                raise ValueError(Constants.artist_requires_package)
            PricingPackage.remove(package_id=params.package_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Package deleted successfully')
        )

    @Common(response_handler=PackageResponseSerializer).exception_handler
    def get_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        pkg = PricingPackage.get(package_id=params.package_id)
        if not pkg or pkg['artist_id'] != profile.artist_id:
            raise ValueError(self.data_no_match)
        data = self._build_package_response(pkg)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=PackageResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id, artist_id=params.artist_id)
        reversed_mapped = ArtistsUtils.reverse_mapper('package', [params.sort_by, params.filter_key])
        pages = Paginator(
            PricingPackage.get_all(
                artist_id=profile.artist_id,
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
        page_data = list(pages.page(params.page_num))
        utils = ArtistsUtils(entity='package')
        data = json.loads(utils.mapper(page_data))
        for i, pkg_dict in enumerate(page_data):
            inclusions_raw = PackageInclusion.get_for_package(package_id=pkg_dict['package_id'])
            inc_utils = ArtistsUtils(entity='inclusion')
            data[i]['inclusions'] = json.loads(inc_utils.mapper(inclusions_raw))
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
