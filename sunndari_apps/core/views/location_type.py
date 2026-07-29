import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.core.models.location_type import LocationType
from sunndari_apps.core.serializers.response.get.get_location_type import LocationTypeResponseGetSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_location_type import LocationTypeResponseGetAllSerializer
from sunndari_apps.core.utils import CoreUtils
from sunndari.constants import Constants


class LocationTypeView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    @Common(response_handler=LocationTypeResponseGetSerializer).exception_handler
    def get_extract(self, params):
        location_type = LocationType.get(location_type_id=params.location_type_id)
        if not location_type:
            raise ValueError(self.data_no_match)
        utils = CoreUtils(entity='location_type', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([location_type]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=LocationTypeResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = CoreUtils.reverse_mapper('location_type', [params.sort_by, params.filter_key])
        pages = Paginator(
            LocationType.get_all(
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
        utils = CoreUtils(entity='location_type', columns_required=[c for c in params.values.split(',') if c])
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
