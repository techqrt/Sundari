import json
from datetime import timedelta
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.dataclasses.request.get.get_booking import GetArtistBookingRequest
from sunndari_apps.artists.dataclasses.request.update.update_booking_status import UpdateBookingStatusRequest
from sunndari_apps.artists.dataclasses.request.update.on_my_way import OnMyWayRequest
from sunndari_apps.artists.dataclasses.request.update.arrived import ArrivedRequest
from sunndari_apps.artists.dataclasses.request.update.verify_start_pin import VerifyStartPinRequest
from sunndari_apps.artists.dataclasses.request.update.verify_completion_pin import VerifyCompletionPinRequest
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.payment import Payment
from sunndari_apps.customers.utils import CustomersUtils
from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
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
        Booking.with_display_expiry([booking])
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
        Booking.with_display_expiry(page_data)
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

        # Accepting is the only forward-progressing move this generic endpoint can make
        # (cancelling/no-show are closing moves, always allowed even on an expired
        # booking) — block it once the booking's own window has elapsed, rather than
        # waiting for the sweep cron to catch up.
        if params.status == 'confirmed' and Booking.is_past_missed_deadline(booking['booking_date'], booking['start_time']):
            raise ValueError(Constants.booking_expired)

        allowed = Booking.ARTIST_TRANSITIONS.get(current_status, [])
        if params.status not in allowed:
            next_steps = ', '.join(f"'{s}'" for s in allowed) if allowed else 'none — this booking is in a final state'
            raise ValueError(
                f"Cannot set status to '{params.status}' — booking is currently '{current_status}'. "
                f"Allowed next status: {next_steps}."
            )

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
        if params.status == 'cancelled':
            NotificationService.notify(
                user_id=booking['customer_id'],
                title='Booking cancelled',
                message=f"Your booking for {booking['booking_date']} was cancelled by the artist.",
                type='booking_cancelled',
                booking_id=params.booking_id,
            )
        if params.status == 'completed':
            ChatService.close_conversation(booking_id=params.booking_id)
            NotificationService.notify(
                user_id=booking['customer_id'],
                title='Booking completed',
                message=f"Your booking for {booking['booking_date']} is complete.",
                type='booking_completed',
                booking_id=params.booking_id,
            )
        if params.status == 'no_show':
            NotificationService.notify(
                user_id=booking['customer_id'],
                title='Marked as no-show',
                message=f"You were marked as a no-show for your booking on {booking['booking_date']}.",
                type='booking_no_show',
                booking_id=params.booking_id,
            )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Booking status updated successfully')
        )

    @Common().exception_handler
    def on_my_way_extract(self, params: OnMyWayRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)

        current_status = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if current_status != 'confirmed' or booking['on_my_way_at'] is not None:
            raise ValueError(Constants.on_my_way_not_allowed)

        if Booking.is_past_missed_deadline(booking['booking_date'], booking['start_time']):
            raise ValueError(Constants.booking_expired)

        booking_start = Booking.to_aware(booking['booking_date'], booking['start_time'])
        window_opens_at = booking_start - timedelta(hours=Configurations.on_my_way_window_hours)
        if timezone.now() < window_opens_at:
            raise ValueError(Constants.on_my_way_too_early)

        Booking.mark_on_my_way(booking_id=params.booking_id)
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Your artist is on the way',
            message=f"Your artist is on the way for your booking on {booking['booking_date']}.",
            type='artist_on_the_way',
            booking_id=params.booking_id,
        )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Marked as on the way')
        )

    @Common().exception_handler
    def arrived_extract(self, params: ArrivedRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)

        current_status = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if current_status != 'confirmed' or booking['on_my_way_at'] is None or booking['arrived_at'] is not None:
            raise ValueError(Constants.arrived_not_allowed)

        if Booking.is_past_missed_deadline(booking['booking_date'], booking['start_time']):
            raise ValueError(Constants.booking_expired)

        if Booking.is_booking_otp_locked(booking_id=params.booking_id):
            raise ValueError(Constants.account_locked)

        otp_valid = (
            booking['booking_otp'] is not None
            and booking['booking_otp'] == params.booking_otp
            and booking['booking_otp_expiry'] is not None
            and timezone.now() <= booking['booking_otp_expiry']
        )
        if not otp_valid:
            Booking.record_booking_otp_failure(booking_id=params.booking_id)
            raise ValueError(Constants.otp_invalid)

        Booking.confirm_arrival(
            booking_id=params.booking_id, booking_date=booking['booking_date'], end_time=booking['end_time'],
        )
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Your artist has arrived',
            message=f"Your artist has arrived for your booking on {booking['booking_date']}.",
            type='artist_arrived',
            booking_id=params.booking_id,
        )
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Start Service PIN ready',
            message='Share your Start Service PIN with the artist to begin the service.',
            type='start_pin_ready',
            booking_id=params.booking_id,
        )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Arrival confirmed')
        )

    @Common().exception_handler
    def verify_start_pin_extract(self, params: VerifyStartPinRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)

        current_status = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if current_status != 'confirmed' or booking['arrived_at'] is None:
            raise ValueError(Constants.start_pin_verify_not_allowed)

        # No missed-deadline guard here, deliberately: arrived_at can only have been set
        # by a real, OTP-verified, timestamped arrival that itself already had to happen
        # before the deadline (arrived_extract enforces that). Once that legitimate
        # on-site interaction has begun, blocking its next step just because the clock
        # ticked over while the customer looked up their PIN would strand a real
        # appointment — the same failure mode already ruled out for in_progress bookings.

        if Booking.is_start_pin_locked(booking_id=params.booking_id):
            raise ValueError(Constants.account_locked)

        pin_valid = (
            booking['start_service_pin'] is not None
            and booking['start_service_pin'] == params.start_service_pin
            and booking['start_pin_expiry'] is not None
            and timezone.now() <= booking['start_pin_expiry']
        )
        if not pin_valid:
            Booking.record_start_pin_failure(booking_id=params.booking_id)
            raise ValueError(Constants.start_pin_invalid)

        in_progress_status = BookingStatus.objects.filter(name='in_progress').first()
        Booking.start_service(
            booking_id=params.booking_id,
            in_progress_status_id=in_progress_status.status_id,
            booking_date=booking['booking_date'],
            end_time=booking['end_time'],
        )
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Service started',
            message=f"Your service for the booking on {booking['booking_date']} has started.",
            type='service_started',
            booking_id=params.booking_id,
        )
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Completion PIN ready',
            message='Share your Completion PIN with the artist once the service is finished.',
            type='completion_pin_ready',
            booking_id=params.booking_id,
        )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Service started')
        )

    @Common().exception_handler
    def verify_completion_pin_extract(self, params: VerifyCompletionPinRequest):
        artist_id = self._get_artist_id(user_id=params.user_id)
        booking = Booking.get_lifecycle_state(booking_id=params.booking_id)
        if not booking or booking['artist_id'] != artist_id:
            raise ValueError(Constants.booking_not_found)

        current_status = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if current_status != 'in_progress':
            raise ValueError(Constants.completion_pin_verify_not_allowed)

        if Booking.is_completion_pin_locked(booking_id=params.booking_id):
            raise ValueError(Constants.account_locked)

        pin_valid = (
            booking['completion_pin'] is not None
            and booking['completion_pin'] == params.completion_pin
            and booking['completion_pin_expiry'] is not None
            and timezone.now() <= booking['completion_pin_expiry']
        )
        if not pin_valid:
            Booking.record_completion_pin_failure(booking_id=params.booking_id)
            raise ValueError(Constants.completion_pin_invalid)

        completed_status = BookingStatus.objects.filter(name='completed').first()
        Booking.complete_service(booking_id=params.booking_id, completed_status_id=completed_status.status_id)
        ChatService.close_conversation(booking_id=params.booking_id)
        NotificationService.notify(
            user_id=booking['customer_id'],
            title='Booking completed',
            message=f"Your booking for {booking['booking_date']} is complete.",
            type='booking_completed',
            booking_id=params.booking_id,
        )
        BookingFirebaseUtils.sync_booking(booking_id=params.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Service completed')
        )
