from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.artists.serializers.request.create.initiate_registration_payment import (
    InitiateRegistrationPaymentSerializer,
)
from sunndari_apps.artists.serializers.request.create.validate_promo_code import ValidatePromoCodeSerializer
from sunndari_apps.artists.serializers.request.get.get_registration_fee import GetRegistrationFeeSerializer
from sunndari_apps.artists.serializers.response.get.get_registration_fee import (
    InitiateRegistrationPaymentResponseSerializer, PromoQuoteResponseSerializer, RegistrationFeeResponseSerializer,
)
from sunndari_apps.artists.views.registration_payment import ArtistRegistrationPaymentView
from sunndari_apps.payments.serializers.request.update.verify_payment import VerifyPaymentSerializer


class ArtistRegistrationPaymentController:

    @extend_schema(
        description=(
            'The artist registration fee and whether this artist still has to pay it. The fee must be paid '
            'before onboarding can be submitted for review (artists approved earlier are exempt).'
        ),
        parameters=GetRegistrationFeeSerializer.get_parameters(),
        responses=SwaggerPage.response(response=RegistrationFeeResponseSerializer),
        tags=['Artists - Registration Fee'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetRegistrationFeeSerializer).validate
    def get_fee(request: Request) -> Response:
        return ArtistRegistrationPaymentView().get_fee_extract(params=request.params)

    @extend_schema(
        description=(
            'Preview the registration fee with a promo code: discount and payable amount, calculated on the '
            'server. Nothing is recorded; the code is reserved only when the payment is started.'
        ),
        request=ValidatePromoCodeSerializer,
        responses=SwaggerPage.response(response=PromoQuoteResponseSerializer),
        tags=['Artists - Registration Fee'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ValidatePromoCodeSerializer).validate
    def validate_promo(request: Request) -> Response:
        return ArtistRegistrationPaymentView().validate_promo_extract(params=request.params)

    @extend_schema(
        description=(
            'Start paying the registration fee, optionally with a promo code. The server works out every amount. '
            'With a payable amount above zero this returns a Razorpay order to pay (same fields as the booking '
            'payment initiate); a repeat call for the same promo returns the open order. A 100% promo completes '
            'the registration at once with no gateway order (fully_covered_by_promo=true, amount=0). '
            'Starting a payment does not complete it: it is confirmed only once Razorpay\'s payment is verified.'
        ),
        request=InitiateRegistrationPaymentSerializer,
        responses=SwaggerPage.response(response=InitiateRegistrationPaymentResponseSerializer),
        tags=['Artists - Registration Fee'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=InitiateRegistrationPaymentSerializer).validate
    def initiate_payment(request: Request) -> Response:
        return ArtistRegistrationPaymentView().initiate_extract(params=request.params)

    @extend_schema(
        description=(
            'Call right after Razorpay Checkout succeeds for a registration payment. The server checks the '
            'signature and independently confirms with Razorpay that the payment was captured for the exact '
            'amount of the order; only then is the registration fee marked paid. Safe to repeat. A payment that '
            'cannot be applied (for example the fee was already paid another way) is refunded automatically.'
        ),
        request=VerifyPaymentSerializer,
        responses=SwaggerPage.response(description='Payment verified successfully'),
        tags=['Artists - Registration Fee'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=VerifyPaymentSerializer).validate
    def verify_payment(request: Request) -> Response:
        return ArtistRegistrationPaymentView().verify_extract(params=request.params)
