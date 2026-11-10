import logging

import razorpay
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment
from sunndari_apps.artists.registration_fee import RegistrationFee
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.artists.serializers.response.get.get_registration_fee import (
    InitiateRegistrationPaymentResponseSerializer, PromoQuoteResponseSerializer, RegistrationFeeResponseSerializer,
)


logger = logging.getLogger(__name__)


def _money(value) -> str:
    return f'{value:.2f}'


class ArtistRegistrationPaymentView:

    @staticmethod
    def _profile(user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common(response_handler=RegistrationFeeResponseSerializer).exception_handler
    def get_fee_extract(self, params):
        profile = self._profile(params.user_id)
        paid_at = ArtistRegistrationPayment.objects.filter(
            artist_id=profile.artist_id, paid_at__isnull=False, refund_requested_at__isnull=True,
        ).values_list('paid_at', flat=True).first()
        paid = paid_at is not None
        data = {
            'feeAmount': _money(RegistrationFee.fee()),
            'currency': Configurations.razorpay_currency,
            'paid': paid,
            'exempt': profile.registration_fee_exempt,
            'registrationRequired': not paid and not profile.registration_fee_exempt,
            'paidAt': paid_at,
        }
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))

    @Common(response_handler=PromoQuoteResponseSerializer).exception_handler
    def validate_promo_extract(self, params):
        """Read-only preview of what the artist would pay with this code. Records nothing; the code is
        only reserved when the payment is started."""
        profile = self._profile(params.user_id)
        if profile.registration_fee_exempt or RegistrationFee.is_paid(profile.artist_id):
            raise ValueError(Constants.registration_fee_not_required)
        quote = RegistrationFee.quote(profile.artist_id, params.promo_code)
        data = {
            'promoCode': quote['promo'].code,
            'feeAmount': _money(quote['fee']),
            'discountPercent': _money(quote['discount_percent']),
            'discountAmount': _money(quote['discount']),
            'payableAmount': _money(quote['payable']),
            'currency': Configurations.razorpay_currency,
            'requiresPayment': quote['payable'] > 0,
        }
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.promo_applied, data=data))

    @Common(response_handler=InitiateRegistrationPaymentResponseSerializer).exception_handler
    def initiate_extract(self, params):
        data, created = RegistrationPaymentService.initiate(user_id=params.user_id, promo_code=params.promo_code)
        if data['fully_covered_by_promo']:
            message = Constants.registration_free_completed
        elif created:
            message = Constants.registration_payment_initiated
        else:
            message = Constants.registration_payment_reused
        return Response(
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            data=Utils.success_response_data(message=message, data=data),
        )

    @Common().exception_handler
    def verify_extract(self, params):
        """Called by the app right after Razorpay Checkout succeeds. Like booking verify, it re-establishes that
        the payment is real with two independent checks: the signature (the values were not made up by the
        client) and a live Razorpay lookup (the payment exists, was captured, and matches the order we made,
        in amount and currency). The artist is only marked paid by RegistrationPaymentService.settle, and a
        payment that belongs to someone else is reported as not found."""
        payment = ArtistRegistrationPayment.objects.select_related('artist', 'status').filter(
            gateway_order_id=params.razorpay_order_id,
        ).first()
        if payment is None or payment.artist.user_id != params.user_id:
            raise ValueError(Constants.payment_not_found)
        if payment.status.name in ('refunded', 'partially_refunded') or payment.refund_requested_at is not None:
            raise ValueError(Constants.payment_not_verifiable)
        if payment.paid_at is not None:
            return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Payment already verified'))

        client = RazorpayGateway.get_client()
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': params.razorpay_order_id,
                'razorpay_payment_id': params.razorpay_payment_id,
                'razorpay_signature': params.razorpay_signature,
            })
        except razorpay.errors.SignatureVerificationError:
            logger.warning('Registration payment %s: signature verification failed', payment.registration_payment_id)
            raise ValueError(Constants.payment_signature_invalid)

        try:
            razorpay_payment = client.payment.fetch(params.razorpay_payment_id)
            razorpay_order = client.order.fetch(params.razorpay_order_id)
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError):
            raise ValueError(Constants.payment_verification_mismatch)

        # The amount is checked against the order we created (what the client cannot inflate), exactly as
        # booking verify does, because the gateway may add its own fee to the payment itself.
        expected_paise = int(round(payment.payable_amount * 100))
        is_valid = (
            razorpay_payment.get('order_id') == params.razorpay_order_id
            and razorpay_payment.get('status') == 'captured'
            and razorpay_payment.get('currency', Configurations.razorpay_currency) == Configurations.razorpay_currency
            and razorpay_order.get('amount') == expected_paise
            and razorpay_order.get('amount_paid') == razorpay_order.get('amount')
            and razorpay_order.get('status') == 'paid'
        )
        if not is_valid:
            raise ValueError(Constants.payment_verification_mismatch)

        outcome = RegistrationPaymentService.settle(
            registration_payment_id=payment.registration_payment_id, gateway_payment_id=params.razorpay_payment_id,
        )
        if outcome == RegistrationPaymentService.APPLIED:
            RegistrationPaymentService.notify_paid(params.user_id)
        elif outcome != RegistrationPaymentService.ALREADY_APPLIED:
            raise ValueError(Constants.registration_payment_not_applied)
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Payment verified successfully'))
