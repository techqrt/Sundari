import json
from django.core.paginator import Paginator
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.authentication.models import User
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.customer_review import CustomerReview
from sunndari.constants import Constants


class ArtistCustomerReviewView:
    """Artist -> customer ratings. Only the artist who served a completed booking can write
    one, once per booking; they are private to the artist's side (a customer never sees them)."""

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def create_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            booking = Booking.objects.select_for_update().select_related('status').filter(
                booking_id=params.booking_id,
            ).first()
            if not booking or booking.artist_id != profile.artist_id:
                raise ValueError(Constants.booking_not_found)
            if booking.status.name != 'completed':
                raise ValueError(Constants.booking_not_completed)
            if CustomerReview.objects.filter(booking_id=booking.booking_id).exists():
                raise ValueError(Constants.booking_already_reviewed)
            review = CustomerReview.objects.create(
                booking_id=booking.booking_id, artist_id=profile.artist_id, customer_id=booking.customer_id,
                rating=params.rating, comment=params.comment or None,
            )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Customer review submitted successfully',
                data={'customer_review_id': review.customer_review_id},
            )
        )

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id)
        qs = CustomerReview.objects.filter(artist_id=profile.artist_id)
        if params.filter_key == 'bookingId' and params.filter_value.isdigit():
            qs = qs.filter(booking_id=int(params.filter_value))
        if params.filter_key == 'customerId' and params.filter_value.isdigit():
            qs = qs.filter(customer_id=int(params.filter_value))
        qs = qs.order_by('-created_at', '-customer_review_id')
        pages = Paginator(list(qs.values(
            'customer_review_id', 'booking_id', 'customer_id', 'rating', 'comment', 'created_at',
        )), per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        rows = list(pages.page(params.page_num))
        names = dict(User.objects.filter(user_id__in=[r['customer_id'] for r in rows]).values_list('user_id', 'name'))
        data = [{
            'customerReviewId': r['customer_review_id'], 'bookingId': r['booking_id'], 'customerId': r['customer_id'],
            'customerName': names.get(r['customer_id']), 'rating': r['rating'], 'comment': r['comment'],
            'createdAt': r['created_at'],
        } for r in rows]
        data = Utils.add_page_parameter(
            final_data=json.loads(json.dumps(data, default=str)),
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )
