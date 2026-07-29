import json
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.serializers.response.get_all.get_all_statuses import StatusListResponseSerializer
from sunndari_apps.core.utils import CoreUtils
from sunndari.constants import Constants


class StatusesView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _map_statuses(self, raw: list) -> list:
        utils = CoreUtils(entity='status')
        return json.loads(utils.mapper(raw))

    @Common(response_handler=StatusListResponseSerializer).exception_handler
    def get_booking_statuses(self, params):
        data = self._map_statuses(BookingStatus.get_all())
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=StatusListResponseSerializer).exception_handler
    def get_payment_statuses(self, params):
        data = self._map_statuses(PaymentStatus.get_all())
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=StatusListResponseSerializer).exception_handler
    def get_approval_statuses(self, params):
        data = self._map_statuses(ApprovalStatus.get_all())
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
