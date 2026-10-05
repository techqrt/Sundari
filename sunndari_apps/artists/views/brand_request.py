import json
from django.core.paginator import Paginator
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.brand_request import BrandRequest
from sunndari_apps.core.models.brand import Brand
from sunndari.constants import Constants

MAX_PENDING_REQUESTS = 5


class ArtistBrandRequestView:

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def create_extract(self, params):
        name = params.name.strip()
        if not name:
            raise ValueError('Brand name is required')
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            if Brand.name_exists(name):
                raise ValueError(Constants.brand_exists)
            pending = BrandRequest.objects.filter(artist_id=profile.artist_id, status='pending')
            if pending.filter(name__iexact=name).exists():
                raise ValueError(Constants.brand_request_exists)
            if pending.count() >= MAX_PENDING_REQUESTS:
                raise ValueError(Constants.brand_request_limit)
            request = BrandRequest.objects.create(artist_id=profile.artist_id, name=name)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Brand request submitted', data={'request_id': request.request_id}),
        )

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id)
        pages = Paginator(
            list(BrandRequest.objects.filter(artist_id=profile.artist_id).order_by('-created_at', '-request_id')),
            per_page=params.limit,
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        data = [{
            'requestId': r.request_id, 'name': r.name, 'status': r.status, 'adminNote': r.admin_note,
            'decidedAt': r.decided_at, 'createdAt': r.created_at,
        } for r in pages.page(params.page_num)]
        data = Utils.add_page_parameter(
            final_data=json.loads(json.dumps(data, default=str)), page_num=params.page_num, total_page=pages.num_pages,
            present_url=params.present_url, next_page_required=pages.num_pages != params.page_num,
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))
