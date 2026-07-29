import json
from django.db import transaction
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.users.models.customer_address import CustomerAddress
from sunndari_apps.users.dataclasses.request.create.create_address import CustomerAddressCreateRequest
from sunndari_apps.users.dataclasses.request.update.update_address import CustomerAddressUpdateRequest
from sunndari_apps.users.serializers.response.get.get_address import CustomerAddressResponseGetSerializer
from sunndari_apps.users.serializers.response.get_all.get_all_address import CustomerAddressResponseGetAllSerializer
from sunndari_apps.users.utils import UsersUtils
from sunndari.constants import Constants


class CustomerAddressView:
    def __init__(self):
        self.create_msg = 'Address added successfully'
        self.update_msg = 'Address updated successfully'
        self.delete_msg = 'Address deleted successfully'
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    @Common().exception_handler
    def create_extract(self, params: CustomerAddressCreateRequest):
        with transaction.atomic():
            if CustomerAddress.count_for_user(user_id=params.user_id) >= 5:
                raise ValueError(Constants.address_limit_exceeded)
            obj = CustomerAddress()
            address_id = obj.create(
                user_id=params.user_id,
                address_line_1=params.address_line_1,
                address_line_2=params.address_line_2,
                city=params.city,
                pin_code=params.pin_code,
                is_default=params.is_default,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message=self.create_msg, data={'address_id': address_id})
        )

    @Common().exception_handler
    def update_extract(self, params: CustomerAddressUpdateRequest):
        with transaction.atomic():
            address = CustomerAddress.get(address_id=params.address_id)
            if not address:
                raise ValueError(self.data_no_match)
            if address['user_id'] != params.user_id:
                raise ValueError(Constants.forbidden_resource)
            CustomerAddress.update(
                address_id=params.address_id,
                address_line_1=params.address_line_1,
                address_line_2=params.address_line_2,
                city=params.city,
                pin_code=params.pin_code,
                is_default=params.is_default,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.update_msg)
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            address = CustomerAddress.get(address_id=params.address_id)
            if not address:
                raise ValueError(self.data_no_match)
            if address['user_id'] != params.user_id:
                raise ValueError(Constants.forbidden_resource)
            CustomerAddress.remove(address_id=params.address_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.delete_msg)
        )

    @Common(response_handler=CustomerAddressResponseGetSerializer).exception_handler
    def get_extract(self, params):
        with transaction.atomic():
            address = CustomerAddress.get(address_id=params.address_id)
            if not address:
                raise ValueError(self.data_no_match)
            if address['user_id'] != params.user_id:
                raise ValueError(Constants.forbidden_resource)
            utils = UsersUtils(entity='address', columns_required=[c for c in params.values.split(',') if c])
            data = json.loads(utils.mapper([address]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=CustomerAddressResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = UsersUtils.reverse_mapper([params.sort_by, params.filter_key])
        pages = Paginator(
            CustomerAddress.get_all(
                user_id=params.user_id,
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
        utils = UsersUtils(entity='address', columns_required=[c for c in params.values.split(',') if c])
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
