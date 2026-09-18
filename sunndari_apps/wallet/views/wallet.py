import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet
from sunndari_apps.wallet.models.coin_transaction import CoinTransaction
from sunndari_apps.wallet.dataclasses.request.get.get_wallet import GetWalletRequest
from sunndari_apps.wallet.serializers.response.get.wallet import WalletResponseSerializer
from sunndari_apps.wallet.serializers.response.get_all.transaction import TransactionResponseGetAllSerializer
from sunndari_apps.wallet.utils import WalletUtils
from sunndari.constants import Constants


class WalletView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=WalletResponseSerializer).exception_handler
    def get_extract(self, params: GetWalletRequest):
        # A customer who has never earned/spent a coin yet still has a wallet, logically
        # — surface it as a real zero-balance record rather than a 404, matching how a
        # brand-new customer's balance is treated everywhere else in this feature.
        CustomerWallet.get_or_create_for_customer(customer_id=params.user_id)
        wallet = CustomerWallet.get(customer_id=params.user_id)
        utils = WalletUtils(entity='wallet', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([wallet]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=TransactionResponseGetAllSerializer).exception_handler
    def get_all_transactions_extract(self, params: GetAll):
        # CustomerWallet.customer is the PK, so a wallet's id is always the owning
        # customer's user_id — no need to look the wallet up first just to get its id.
        reversed_mapped = WalletUtils.reverse_mapper('transaction', [params.sort_by, params.filter_key])
        raw = CoinTransaction.get_all(
            wallet_id=params.user_id,
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
        utils = WalletUtils(entity='transaction')
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
