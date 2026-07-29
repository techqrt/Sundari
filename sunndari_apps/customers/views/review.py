import json
from django.core.paginator import Paginator
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.review import Review
from sunndari_apps.customers.dataclasses.request.create.create_review import CreateReviewRequest
from sunndari_apps.customers.dataclasses.request.get.get_review import GetReviewRequest
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.customers.serializers.response.get.get_review import ReviewResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_review import ReviewResponseGetAllSerializer
from sunndari.constants import Constants


class ReviewView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common().exception_handler
    def create_extract(self, params: CreateReviewRequest):
        with transaction.atomic():
            booking = Booking.get(booking_id=params.booking_id)
            if not booking or booking['customer_id'] != params.user_id:
                raise ValueError(Constants.booking_not_found)

            status_name = BookingStatus.objects.filter(
                status_id=booking['status_id'],
            ).values_list('name', flat=True).first()
            if status_name != 'completed':
                raise ValueError(Constants.booking_not_completed)

            if Review.exists_for_booking(booking_id=params.booking_id):
                raise ValueError(Constants.booking_already_reviewed)

            review_id = Review().create(
                booking_id=params.booking_id,
                customer_id=params.user_id,
                artist_id=booking['artist_id'],
                rating=params.rating,
                comment=params.comment or None,
            )
            ArtistProfile.record_review(artist_id=booking['artist_id'], rating=params.rating)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Review submitted successfully', data={'review_id': review_id})
        )

    @Common(response_handler=ReviewResponseSerializer).exception_handler
    def get_extract(self, params: GetReviewRequest):
        review = Review.get(review_id=params.review_id)
        if not review:
            raise ValueError(Constants.item_not_found)
        utils = CustomersUtils(entity='review', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([review]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=ReviewResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = CustomersUtils.reverse_mapper('review', [params.sort_by, params.filter_key])
        raw = Review.get_all(
            artist_id=params.artist_id,
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
        utils = CustomersUtils(entity='review')
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
