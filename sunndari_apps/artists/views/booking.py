import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.dataclasses.request.get.get_booking import GetArtistBookingRequest
from sunndari_apps.artists.dataclasses.request.update.update_booking_status import UpdateBookingStatusRequest
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.payment import Payment
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.chat.services import ChatService
from sunndari_apps.customers.serializers.response.get.get_booking import BookingResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_booking import BookingResponseGetAllSerializer
from sunndari.constants import Constants


class ArtistBookingView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _get_artist_id(self, user_id: int) -> int:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile.artist_id

    @Common(response_handler=BookingResponseSerializer).exception_handler
    def get_extract(self, params: GetArtistBookingRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)
        utils = CustomersUtils(entity='booking', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([booking]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=BookingResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        artist_id = self._get_artist_id(user_id=params.user_id)
        reversed_mapped = CustomersUtils.reverse_mapper('booking', [params.sort_by, params.filter_key])
        raw = Booking.get_all(
            artist_id=artist_id,
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
        utils = CustomersUtils(entity='booking')
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

    @Common().exception_handler
    def update_status_extract(self, params: UpdateBookingStatusRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)

        current_status = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        allowed = Booking.ARTIST_TRANSITIONS.get(current_status, [])
        if params.status not in allowed:
            raise ValueError(Constants.update_not_allowed)

        new_status = BookingStatus.objects.filter(name=params.status).first()
        Booking.update_status(
            booking_id=params.booking_id,
            status_id=new_status.status_id,
            cancelled_by='artist' if params.status == 'cancelled' else None,
            cancellation_reason=(params.reason or None) if params.status == 'cancelled' else None,
        )
        if params.status == 'cancelled':
            refunded_status = PaymentStatus.objects.filter(name='refunded').first()
            if refunded_status:
                Payment.mark_refunded(booking_id=params.booking_id, status_id=refunded_status.status_id)
        if params.status == 'confirmed':
            NotificationService.notify(
                user_id=booking['customer_id'],
                title='Booking confirmed',
                message=f"Your booking for {booking['booking_date']} has been confirmed.",
                type='booking_confirmed',
                booking_id=params.booking_id,
            )
        if params.status == 'completed':
            ChatService.close_conversation(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Booking status updated successfully')
        )
