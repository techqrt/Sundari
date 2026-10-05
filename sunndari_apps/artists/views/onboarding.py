import json
from django.core.paginator import Paginator
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.common.exceptions.validation_errors import ValidationErrors
from sunndari_apps.authentication.models import User
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.availability_schedule import ArtistAvailabilitySchedule
from sunndari_apps.artists.models.artist_location_preference import ArtistLocationPreference
from sunndari_apps.artists.models.document import ArtistDocument
from sunndari_apps.artists.models.portfolio import Portfolio
from sunndari_apps.artists.models.review_feedback import ArtistReviewFeedback
from sunndari_apps.artists.models.payout_account import ArtistPayoutAccount
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.artists.serializers.response.get.get_onboarding_status import OnboardingStatusResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_review_feedback import (
    ReviewFeedbackResponseGetAllSerializer,
)
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants

STEP_LABELS = {
    'basicInfo': 'Basic info (name, bio, city)',
    'location': 'Base address/location',
    'services': 'At least one active pricing package',
    'availability': 'Availability schedule and location preference',
    'registrationFields': 'Registration details (display name, date of birth, profile type)',
    'workSamples': 'At least one work sample photo for admin review',
    'documents': 'Identity/verification document',
    'payoutAccount': 'Payout bank account',
    'agreement': 'Partner agreement acceptance',
}


class ArtistOnboardingView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _get_profile_row(self, user_id: int) -> dict:
        profile = ArtistProfile.get(user_id=user_id)
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    def _compute_steps(self, profile: dict, user_row: dict) -> dict:
        artist_id = profile['artist_id']
        return {
            'basicInfo': bool(profile['bio'] and profile['city'] and user_row and user_row['name']),
            'location': profile['base_address_id'] is not None,
            'services': PricingPackage.active_count(artist_id=artist_id) >= 1,
            'availability': (
                ArtistAvailabilitySchedule.objects.filter(artist_id=artist_id, is_active=True).exists()
                and ArtistLocationPreference.objects.filter(artist_id=artist_id).exists()
            ),
            'registrationFields': bool(
                profile['display_name'] and profile['date_of_birth'] and profile['profile_type']
            ),
            'workSamples': Portfolio.count_work_samples(artist_id=artist_id) >= 1,
            'documents': ArtistDocument.has_type(artist_id=artist_id, document_type='id_proof'),
            'payoutAccount': ArtistPayoutAccount.get(artist_id=artist_id) is not None,
            'agreement': profile['terms_accepted_at'] is not None,
        }

    def _compute_status(self, profile: dict, steps: dict) -> str:
        approval_name = ApprovalStatus.objects.filter(
            status_id=profile['approval_status_id']
        ).values_list('name', flat=True).first()
        if approval_name in ('approved', 'rejected', 'suspended'):
            return approval_name
        if profile['submitted_for_review_at'] is not None:
            return 'submitted'
        if any(steps.values()):
            return 'in_progress'
        return 'not_started'

    @staticmethod
    def _latest_feedback(artist_id: int):
        row = ArtistReviewFeedback.get_latest(artist_id=artist_id)
        if not row:
            return None
        return {
            'feedbackId': row['feedback_id'], 'decision': row['decision'],
            'message': row['message'], 'createdAt': row['created_at'],
        }

    @Common(response_handler=OnboardingStatusResponseSerializer).exception_handler
    def get_status_extract(self, params):
        profile = self._get_profile_row(user_id=params.user_id)
        user_row = User.get(user_id=params.user_id)
        steps = self._compute_steps(profile=profile, user_row=user_row)
        overall_status = self._compute_status(profile=profile, steps=steps)
        data = {
            'status': overall_status,
            'steps': steps,
            'submittedForReviewAt': profile['submitted_for_review_at'],
            'latestFeedback': self._latest_feedback(profile['artist_id']),
        }
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def submit_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile_row(user_id=params.user_id)
            approval_name = ApprovalStatus.objects.filter(
                status_id=profile['approval_status_id']
            ).values_list('name', flat=True).first()
            if approval_name == 'approved':
                raise ValueError(Constants.artist_already_approved)
            if approval_name == 'suspended':
                raise ValueError(Constants.artist_suspended)
            user_row = User.get(user_id=params.user_id)
            steps = self._compute_steps(profile=profile, user_row=user_row)
            missing = [STEP_LABELS[key] for key, done in steps.items() if not done]
            if missing:
                raise ValidationErrors(errors=[f'Incomplete: {label}' for label in missing])
            ArtistProfile.submit_for_review(user_id=params.user_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Onboarding submitted for review')
        )

    @Common(response_handler=ReviewFeedbackResponseGetAllSerializer).exception_handler
    def get_feedback_extract(self, params: GetAll):
        profile = self._get_profile_row(user_id=params.user_id)
        pages = Paginator(
            ArtistReviewFeedback.get_all(artist_id=profile['artist_id'], sort_order=params.sort_order),
            per_page=params.limit,
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = pages.page(params.page_num)
        utils = ArtistsUtils(entity='review_feedback', columns_required=[c for c in params.values.split(',') if c])
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
