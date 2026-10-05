import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.customers.booking_extras import BookingExtras
from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.customers.dataclasses.request.get.get_booking import GetBookingRequest
from sunndari_apps.customers.dataclasses.request.update.cancel_booking import CancelBookingRequest
from sunndari_apps.customers.serializers.response.get.get_booking import BookingResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_booking import BookingResponseGetAllSerializer
from sunndari.constants import Constants


class BookingView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=BookingResponseSerializer).exception_handler
    def get_extract(self, params: GetBookingRequest):
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)
        Booking.with_display_expiry([booking])
        columns = [c for c in params.values.split(',') if c]
        mapper_columns, extra_columns = BookingExtras.split_columns(columns, for_artist=False)
        utils = CustomersUtils(entity='booking', columns_required=mapper_columns)
        data = BookingExtras.attach(
            [booking], [json.loads(utils.mapper([booking]))[0]], for_artist=False, only=extra_columns or None,
        )[0]
        if columns:
            data = {key: data[key] for key in data if key in columns}
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=BookingResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = CustomersUtils.reverse_mapper('booking', [params.sort_by, params.filter_key])
        raw = Booking.get_all(
            customer_id=params.user_id,
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
        Booking.with_display_expiry(page_data)
        utils = CustomersUtils(entity='booking')
        data = BookingExtras.attach(page_data, json.loads(utils.mapper(page_data)), for_artist=False)
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
    def cancel_extract(self, params: CancelBookingRequest):
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)
        status_name = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if status_name not in Booking.ACTIVE_STATUSES:
            raise ValueError(f"This booking cannot be cancelled — it is already '{status_name}'.")
        # ACTIVE_STATUSES is the "blocks the artist's calendar" set and includes in_progress; it is
        # not the "customer may cancel and be refunded" set. Once the artist has arrived (start PIN
        # issued) or the service is running, only the artist/support can end it.
        if status_name == 'in_progress' or booking['arrived_at'] is not None:
            raise ValueError(Constants.booking_not_cancellable)
        cancelled_status = BookingStatus.objects.filter(name='cancelled').first()
        Booking.update_status(
            booking_id=params.booking_id,
            status_id=cancelled_status.status_id,
            cancelled_by='customer',
            cancellation_reason=params.reason or None,
        )
        refunded_status = PaymentStatus.objects.filter(name='refunded').first()
        if refunded_status:
            Payment.mark_refunded(booking_id=params.booking_id, status_id=refunded_status.status_id)

        # Give back any coins redeemed against this booking — cancellation already
        # fully refunds the payment above, so the customer shouldn't also permanently
        # lose the coins for a service they never received.
        CustomerWallet.reverse_all_redemptions_for_booking(booking_id=params.booking_id)

        artist = ArtistProfile.get(artist_id=booking['artist_id'])
        if artist:
            NotificationService.notify(
                user_id=artist['user_id'],
                title='Booking cancelled',
                message=f"Your booking for {booking['booking_date']} was cancelled by the customer.",
                type='booking_cancelled',
                booking_id=params.booking_id,
            )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Booking cancelled successfully')
        )
