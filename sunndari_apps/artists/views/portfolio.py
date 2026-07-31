import json
from django.db import transaction
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.portfolio import Portfolio
from sunndari_apps.artists.serializers.response.get.get_portfolio import PortfolioResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_portfolio import PortfolioResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class PortfolioView:
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

    @Common().exception_handler
    def create_extract(self, params, file):
        if not file:
            raise ValueError(Constants.file_required)
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            if Portfolio.count_active(artist_id=profile.artist_id) >= 20:
                raise ValueError(Constants.portfolio_limit_exceeded)
            obj = Portfolio()
            portfolio_id = obj.create(
                artist_id=profile.artist_id,
                file=file,
                media_type=params.media_type,
                sub_category_id=params.sub_category_id,
                caption=params.caption,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Portfolio item added successfully', data={'portfolio_id': portfolio_id})
        )

    @Common().exception_handler
    def update_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            item = Portfolio.get(portfolio_id=params.portfolio_id)
            if not item or item['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            Portfolio.update(
                portfolio_id=params.portfolio_id,
                caption=params.caption,
                sub_category_id=params.sub_category_id,
                is_active=params.is_active,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Portfolio item updated successfully')
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            item = Portfolio.get(portfolio_id=params.portfolio_id)
            if not item or item['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            Portfolio.remove(portfolio_id=params.portfolio_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Portfolio item deleted successfully')
        )

    @Common(response_handler=PortfolioResponseSerializer).exception_handler
    def get_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        item = Portfolio.get(portfolio_id=params.portfolio_id)
        if not item or item['artist_id'] != profile.artist_id:
            raise ValueError(self.data_no_match)
        utils = ArtistsUtils(entity='portfolio', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([item]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=PortfolioResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id, artist_id=params.artist_id)
        reversed_mapped = ArtistsUtils.reverse_mapper('portfolio', [params.sort_by, params.filter_key])
        pages = Paginator(
            Portfolio.get_all(
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
        page_data = pages.page(params.page_num)
        utils = ArtistsUtils(entity='portfolio', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper(list(page_data)))
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
