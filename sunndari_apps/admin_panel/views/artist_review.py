import json
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.authentication.models import User
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.document import ArtistDocument
from sunndari_apps.artists.models.registration_payment import ArtistRegistrationPayment
from sunndari_apps.artists.models.review_feedback import ArtistReviewFeedback
from sunndari_apps.artists.registration_fee import RegistrationFee
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.admin_panel.dataclasses.request.get.get_all_artists import GetAllArtistsRequest
from sunndari_apps.admin_panel.serializers.response.get_all.get_all_artist import ArtistAdminResponseGetAllSerializer
from sunndari_apps.admin_panel.serializers.response.get_all.get_all_artist_review import (
    ArtistReviewQueueResponseGetAllSerializer,
)
from sunndari.constants import Constants


class AdminArtistReviewView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _require_admin(self, user_id: int) -> None:
        user = User.get(user_id=user_id)
        if not user or user['role'] != 'admin':
            raise ValueError(Constants.forbidden_resource)

    @Common(response_handler=ArtistReviewQueueResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        self._require_admin(user_id=params.user_id)
        reversed_mapped = ArtistsUtils.reverse_mapper('review_queue', [params.sort_by, params.filter_key])
        pages = Paginator(
            ArtistProfile.get_review_queue(
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
        utils = ArtistsUtils(entity='review_queue', columns_required=[c for c in params.values.split(',') if c])
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

    def _get_reviewable_artist(self, artist_id: int) -> dict:
        artist = ArtistProfile.get(artist_id=artist_id)
        if not artist:
            raise ValueError(Constants.artist_not_found)
        # Only artists that actually went through self-service submission may be
        # approved/rejected here — otherwise an admin could activate (or reject) a
        # profile that never finished onboarding, bypassing the whole flow.
        if not artist['submitted_for_review_at']:
            raise ValueError(Constants.onboarding_not_submitted)
        # A suspended artist must be un-suspended through an explicit action, never as a
        # side effect of an approve/reject click on a stale review-queue entry.
        approval_name = ApprovalStatus.objects.filter(
            status_id=artist['approval_status_id'],
        ).values_list('name', flat=True).first()
        if approval_name == 'suspended':
            raise ValueError(Constants.artist_suspended)
        return artist

    @Common().exception_handler
    def approve_extract(self, params):
        with transaction.atomic():
            self._require_admin(user_id=params.user_id)
            self._get_reviewable_artist(artist_id=params.artist_id)
            # Approval does not depend on the registration fee: an artist can be approved with the payment
            # pending, and only the fee decides whether they may switch bookings on.
            if not ArtistDocument.objects.filter(
                artist_id=params.artist_id, document_type='id_proof', verification_status__name='approved',
            ).exists():
                raise ValueError(Constants.kyc_not_verified)
            already = ApprovalStatus.objects.filter(
                status_id=ArtistProfile.get(artist_id=params.artist_id)['approval_status_id'], name='approved',
            ).exists()
            if already:
                # Idempotent: a repeat approval changes nothing, so it must not add another
                # feedback row or send another notification.
                return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message='Artist approved successfully'))
            ArtistProfile.approve(artist_id=params.artist_id)
            artist = ArtistProfile.get(artist_id=params.artist_id)
            ArtistReviewFeedback.record(
                artist_id=params.artist_id, admin_user_id=params.user_id,
                decision='approved', message=params.message,
            )
            NotificationService.notify(
                user_id=artist['user_id'], title='Profile approved',
                message=(
                    'Your artist profile has been approved. You can now receive bookings.'
                    if ArtistProfile.is_eligible(params.artist_id) else
                    'Your artist profile has been approved. Complete your registration payment to start receiving bookings.'
                ),
                type='artist_approved',
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Artist approved successfully')
        )

    @Common().exception_handler
    def reject_extract(self, params):
        with transaction.atomic():
            self._require_admin(user_id=params.user_id)
            self._get_reviewable_artist(artist_id=params.artist_id)
            ArtistProfile.reject(artist_id=params.artist_id, reason=params.reason or None)
            # The registration fee is returned on rejection; the artist pays again to resubmit.
            owed_refund = RegistrationPaymentService.void_for_rejection(params.artist_id)
            artist = ArtistProfile.get(artist_id=params.artist_id)
            ArtistReviewFeedback.record(
                artist_id=params.artist_id, admin_user_id=params.user_id,
                decision='rejected', message=params.reason,
            )
            NotificationService.notify(
                user_id=artist['user_id'], title='Profile needs changes',
                message=params.reason or 'Your artist profile needs changes. Please review and resubmit.',
                type='artist_rejected',
            )
        if owed_refund:
            RegistrationPaymentService.refund(owed_refund)      # calls the gateway, so only after the commit
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Artist rejected')
        )

    @Common().exception_handler
    def set_accepting_extract(self, params):
        """An admin switches an artist's bookings ON or OFF. See ArtistProfile.admin_set_accepting_bookings: OFF
        locks the artist out of switching them back on, ON needs approval and a settled registration payment."""
        self._require_admin(user_id=params.user_id)
        profile, changed = ArtistProfile.admin_set_accepting_bookings(
            artist_id=params.artist_id, accepting=params.is_accepting_bookings,
        )
        if changed:
            NotificationService.notify(
                user_id=profile.user_id, title='Bookings switched on' if profile.is_accepting_bookings else 'Bookings switched off',
                message=(
                    'An admin has switched your bookings back on.' if profile.is_accepting_bookings else
                    'An admin has switched off new bookings for your profile. Contact support to turn them back on.'
                ),
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(
                message='Bookings are now ' + ('on' if profile.is_accepting_bookings else 'off'),
                data={
                    'artistId': profile.artist_id,
                    'isAcceptingBookings': profile.is_accepting_bookings,
                    'acceptingLockedByAdmin': profile.accepting_locked_by_admin,
                },
            )
        )

    ARTIST_SORTS = {'artistId': 'artist_id', 'createdAt': 'created_at', 'name': 'user__name'}

    @Common(response_handler=ArtistAdminResponseGetAllSerializer).exception_handler
    def get_all_artists_extract(self, params: GetAllArtistsRequest):
        """Every artist, whatever their approval state (the review queue only holds those still awaiting a
        decision), each row carrying approval, registration payment, bookings and customer-visibility state. The
        filters combine: approval_status=approved with registration=unpaid lists the approved artists whose
        registration payment is still pending."""
        self._require_admin(user_id=params.user_id)
        paid = Exists(ArtistRegistrationPayment.objects.filter(
            artist_id=OuterRef('artist_id'), paid_at__isnull=False, refund_requested_at__isnull=True,
        ))
        qs = ArtistProfile.objects.select_related('user', 'approval_status').annotate(has_paid=paid)
        if params.approval_status:
            qs = qs.filter(approval_status__name=params.approval_status)
        if params.registration == 'paid':
            qs = qs.filter(has_paid=True)
        elif params.registration == 'exempt':
            qs = qs.filter(registration_fee_exempt=True)
        elif params.registration == 'unpaid':                       # neither paid nor exempt
            qs = qs.filter(has_paid=False, registration_fee_exempt=False)
        if params.accepting is not None:
            qs = qs.filter(is_accepting_bookings=params.accepting)
        if params.search_key:
            qs = qs.filter(
                Q(user__name__icontains=params.search_key) | Q(display_name__icontains=params.search_key)
                | Q(city__icontains=params.search_key) | Q(user__phone_number__icontains=params.search_key)
            )
        sort_field = self.ARTIST_SORTS.get(params.sort_by, 'artist_id')
        descending = params.sort_order == 'desc' if params.sort_by in self.ARTIST_SORTS else True
        qs = qs.order_by(('-' if descending else '') + sort_field, 'artist_id')
        pages = Paginator(qs, per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        rows = []
        for artist in pages.page(params.page_num):
            approval = artist.approval_status.name if artist.approval_status else None
            eligible = artist.registration_fee_exempt or artist.has_paid
            rows.append({
                'artistId': artist.artist_id,
                'userId': artist.user_id,
                'fullName': artist.user.name,
                'displayName': artist.display_name,
                'phoneNumber': artist.user.phone_number,
                'city': artist.city,
                'approvalStatus': approval,
                'registrationFeePaid': artist.has_paid,
                'registrationFeeExempt': artist.registration_fee_exempt,
                'registrationEligible': eligible,
                'isAcceptingBookings': artist.is_accepting_bookings,
                'acceptingLockedByAdmin': artist.accepting_locked_by_admin,
                'visibleToCustomers': approval == 'approved' and artist.is_accepting_bookings and eligible,
                'createdAt': artist.created_at,
            })
        data = Utils.add_page_parameter(
            final_data=json.loads(json.dumps(rows, default=str)),
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def get_detail_extract(self, params):
        """Everything an admin needs to decide on an artist, in one call: registration
        details, specialities and the work-sample photos. Documents have their own endpoint
        (they are sensitive and verified one by one)."""
        from sunndari_apps.artists.models.artist_speciality import ArtistSpeciality
        from sunndari_apps.artists.models.portfolio import Portfolio
        self._require_admin(user_id=params.user_id)
        artist = ArtistProfile.objects.select_related('approval_status').filter(artist_id=params.artist_id).first()
        if not artist:
            raise ValueError(Constants.artist_not_found)
        user = User.get(user_id=artist.user_id)
        data = {
            'artistId': artist.artist_id,
            'userId': artist.user_id,
            'fullName': user['name'] if user else None,
            'displayName': artist.display_name,
            'dateOfBirth': artist.date_of_birth.isoformat() if artist.date_of_birth else None,
            'instagramUrl': artist.instagram_url,
            'profilePhotoUrl': artist.profile_photo.url if artist.profile_photo else None,
            'coverPhotoUrl': artist.cover_photo.url if artist.cover_photo else None,
            'profileType': artist.profile_type,
            'bio': artist.bio,
            'yearsExperience': artist.years_experience,
            'city': artist.city,
            'specialities': [
                {'subCategoryId': row['sub_category_id'], 'name': row['sub_category__name']}
                for row in ArtistSpeciality.get_all(artist_id=artist.artist_id)
            ],
            'workSamples': [
                {'portfolioId': sample.portfolio_id, 'fileUrl': sample.file.url, 'caption': sample.caption}
                for sample in Portfolio.objects.filter(
                    artist_id=artist.artist_id, is_work_sample=True, is_active=True,
                ).order_by('portfolio_id')
            ],
            'approvalStatus': artist.approval_status.name if artist.approval_status else None,
            'portfolioApprovalStatus': artist.portfolio_approval_status,
            'submittedForReviewAt': artist.submitted_for_review_at,
            'registrationFeePaid': RegistrationFee.is_paid(artist.artist_id),
            'registrationFeeExempt': artist.registration_fee_exempt,
            'registrationEligible': ArtistProfile.is_eligible(artist.artist_id),
            'isAcceptingBookings': artist.is_accepting_bookings,
            'acceptingLockedByAdmin': artist.accepting_locked_by_admin,
            'rejectionReason': artist.rejection_reason,
        }
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
