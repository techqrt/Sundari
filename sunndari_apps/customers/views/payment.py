import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.customers.models.payment import Payment
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.customers.dataclasses.request.get.get_payment import GetPaymentRequest
from sunndari_apps.customers.serializers.response.get.get_payment import PaymentResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_payment import PaymentResponseGetAllSerializer
from sunndari.constants import Constants


class PaymentView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=PaymentResponseSerializer).exception_handler
    def get_extract(self, params: GetPaymentRequest):
        payment = Payment.get(payment_id=params.payment_id)
        if not payment or payment['customer_id'] != params.user_id:
            raise ValueError(Constants.payment_not_found)
        utils = CustomersUtils(entity='payment', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([payment]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=PaymentResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = CustomersUtils.reverse_mapper('payment', [params.sort_by, params.filter_key])
        raw = Payment.get_all(
            customer_id=params.user_id,
            sort_by=reversed_mapped.get(params.sort_by, ''),
            sort_order=params.sort_order,
            filter_key=reversed_mapped.get(params.filter_key, ''),
            filter_value=params.filter_value,
            search_key=params.search_key,
        )
        pages = Paginator(raw, per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = list(pages.page(params.page_num))
        utils = CustomersUtils(entity='payment')
        data = json.loads(utils.mapper(page_data))
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
