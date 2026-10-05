import json
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.authentication.models import User
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models.review import Review
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.customers.serializers.response.get_all.get_all_review import ReviewResponseGetAllSerializer
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class ArtistReviewView:
    """The artist's side of customer reviews: read what was written about them and answer it."""

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common(response_handler=ReviewResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id)
        reversed_mapped = CustomersUtils.reverse_mapper('review', [params.sort_by, params.filter_key])
        pages = Paginator(
            Review.get_all(
                artist_id=profile.artist_id,
                sort_by=reversed_mapped.get(params.sort_by, ''),
                sort_order=params.sort_order,
                filter_key=reversed_mapped.get(params.filter_key, ''),
                filter_value=params.filter_value,
                search_key=params.search_key,
            ),
            per_page=params.limit,
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = list(pages.page(params.page_num))
        data = json.loads(CustomersUtils(entity='review').mapper(page_data))
        names = dict(User.objects.filter(
            user_id__in=[row['customer_id'] for row in page_data],
        ).values_list('user_id', 'name'))
        for raw, item in zip(page_data, data):
            item['customerName'] = names.get(raw['customer_id'])
        data = Utils.add_page_parameter(
            final_data=data,
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )

    @Common().exception_handler
    def reply_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            review = Review.objects.select_for_update().filter(review_id=params.review_id).first()
            if not review or review.artist_id != profile.artist_id:
                raise ValueError(Constants.item_not_found)
            first_reply = review.reply is None
            review.reply = params.reply
            review.replied_at = timezone.now()
            review.save()
        if first_reply:
            NotificationService.notify(
                user_id=review.customer_id, title='The artist replied to your review',
                message=params.reply[:140], type='review_reply', booking_id=review.booking_id,
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Reply saved successfully')
        )
