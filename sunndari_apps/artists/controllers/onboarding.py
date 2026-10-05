from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.artists.serializers.request.get.get_onboarding_status import GetOnboardingStatusSerializer
from sunndari_apps.artists.serializers.request.update.submit_onboarding import SubmitOnboardingSerializer
from sunndari_apps.artists.serializers.response.get.get_onboarding_status import OnboardingStatusResponseSerializer
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_review_feedback import (
    ReviewFeedbackResponseGetAllSerializer,
)
from sunndari_apps.artists.views.onboarding import ArtistOnboardingView


class ArtistOnboardingController:

    @extend_schema(
        description='Get own onboarding progress: per-step completion and overall status.',
        parameters=GetOnboardingStatusSerializer.get_parameters(),
        responses=SwaggerPage.response(response=OnboardingStatusResponseSerializer),
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetOnboardingStatusSerializer).validate
    def get_status(request: Request) -> Response:
        return ArtistOnboardingView().get_status_extract(params=request.params)

    @extend_schema(
        description='Submit onboarding for admin review. Requires all steps to be complete.',
        request=SubmitOnboardingSerializer,
        responses=SwaggerPage.response(description='Onboarding submitted for review'),
        tags=['Artists - Onboarding'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SubmitOnboardingSerializer).validate
    def submit(request: Request) -> Response:
        return ArtistOnboardingView().submit_extract(params=request.params)

    @extend_schema(
        description=(
            'History of admin review feedback on own page, oldest first by default (sort_order=desc for newest first). '
            'Each entry is an approval or a rejection with the admin message. To resubmit after a '
            'rejection, call onboarding/submit again.'
        ),
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=ReviewFeedbackResponseGetAllSerializer),
        tags=['Artists - Onboarding'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_feedback(request: Request) -> Response:
        return ArtistOnboardingView().get_feedback_extract(params=request.params)
