import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.core.models.brand import Brand
from sunndari.constants import Constants


class BrandView:

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        qs = Brand.objects.filter(is_active=True)
        if params.search_key:
            qs = qs.filter(name__icontains=params.search_key)
        pages = Paginator(list(qs.order_by('name').values('brand_id', 'name')), per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        data = [{'brandId': row['brand_id'], 'name': row['name']} for row in pages.page(params.page_num)]
        data = Utils.add_page_parameter(
            final_data=data, page_num=params.page_num, total_page=pages.num_pages,
            present_url=params.present_url, next_page_required=pages.num_pages != params.page_num,
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))
