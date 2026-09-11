from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.payments.models import Payment
from sunndari_apps.payments.serializers.response.get_all.payment_type import PaymentTypeListResponseSerializer
from sunndari.constants import Constants


class PaymentTypeView:

    @Common(response_handler=PaymentTypeListResponseSerializer).exception_handler
    def get_all_extract(self, params):
        # payment_type describes what portion of the booking's total this payment covers
        # (full / advance / balance) — it is NOT the payment method (UPI, card, netbanking,
        # etc.), which the gateway's own checkout UI handles and reports back via webhook,
        # not something the backend needs supplied at initiate-payment time.
        data = [{'value': value, 'label': label} for value, label in Payment.PAYMENT_TYPE_CHOICES]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )
