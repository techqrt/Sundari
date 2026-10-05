import json
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.permissions import require_admin
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.core.models.brand import Brand
from sunndari_apps.artists.models.brand_request import BrandRequest
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class AdminBrandView:

    @Common().exception_handler
    def create_extract(self, params):
        require_admin(params.user_id)
        name = params.name.strip()
        if not name:
            raise ValueError('Brand name is required')
        with transaction.atomic():
            if Brand.name_exists(name):
                raise ValueError(Constants.brand_exists)
            brand = Brand.objects.create(name=name)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Brand created successfully', data={'brand_id': brand.brand_id}),
        )

    @Common().exception_handler
    def update_extract(self, params):
        require_admin(params.user_id)
        with transaction.atomic():
            brand = Brand.objects.select_for_update().filter(brand_id=params.brand_id).first()
            if not brand:
                raise ValueError(Constants.data_no_match)
            if params.name is not None:
                name = params.name.strip()
                if not name or Brand.name_exists(name, exclude_brand_id=brand.brand_id):
                    raise ValueError(Constants.brand_exists)
                brand.name = name
            if params.is_active is not None:
                brand.is_active = params.is_active
            brand.save()
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Brand updated successfully'))

    @Common().exception_handler
    def get_all_requests_extract(self, params: GetAll):
        require_admin(params.user_id)
        qs = BrandRequest.objects.select_related('artist__user')
        if params.filter_key == 'status' and params.filter_value:
            qs = qs.filter(status=params.filter_value)
        pages = Paginator(list(qs.order_by('created_at', 'request_id')), per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        data = [{
            'requestId': r.request_id, 'artistId': r.artist_id,
            'artistName': r.artist.display_name or r.artist.user.name, 'name': r.name, 'status': r.status,
            'adminNote': r.admin_note, 'decidedAt': r.decided_at, 'createdAt': r.created_at,
        } for r in pages.page(params.page_num)]
        data = Utils.add_page_parameter(
            final_data=json.loads(json.dumps(data, default=str)), page_num=params.page_num, total_page=pages.num_pages,
            present_url=params.present_url, next_page_required=pages.num_pages != params.page_num,
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))

    @Common().exception_handler
    def decide_extract(self, params):
        require_admin(params.user_id)
        with transaction.atomic():
            request = BrandRequest.objects.select_for_update().select_related('artist').filter(
                request_id=params.request_id,
            ).first()
            if not request:
                raise ValueError(Constants.data_no_match)
            if request.status != 'pending':
                raise ValueError(Constants.brand_request_decided)
            if params.decision == 'approved':
                # The brand may have been added by hand in the meantime — approving is then a no-op, not an error.
                if not Brand.name_exists(request.name):
                    Brand.objects.create(name=request.name)
            request.status = params.decision
            request.admin_note = params.note or None
            request.decided_at = timezone.now()
            request.save()
        NotificationService.notify(
            user_id=request.artist.user_id,
            title='Brand request ' + params.decision,
            message=(f'"{request.name}" was added to the brand list.' if params.decision == 'approved'
                     else f'"{request.name}" was not added. {params.note}'.strip()),
            type=f'brand_request_{params.decision}',
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=f'Brand request {params.decision}'))
