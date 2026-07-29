import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.core.models.service_category import ServiceCategory
from sunndari_apps.core.serializers.response.get.get_service_category import ServiceCategoryResponseGetSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_service_category import ServiceCategoryResponseGetAllSerializer
from sunndari_apps.core.utils import CoreUtils
from sunndari.constants import Constants


class ServiceCategoryView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    @Common(response_handler=ServiceCategoryResponseGetSerializer).exception_handler
    def get_extract(self, params):
        category = ServiceCategory.get(category_id=params.category_id)
        if not category:
            raise ValueError(self.data_no_match)
        utils = CoreUtils(entity='service_category', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([category]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=ServiceCategoryResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = CoreUtils.reverse_mapper('service_category', [params.sort_by, params.filter_key])
        pages = Paginator(
            ServiceCategory.get_all(
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
        utils = CoreUtils(entity='service_category', columns_required=[c for c in params.values.split(',') if c])
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
