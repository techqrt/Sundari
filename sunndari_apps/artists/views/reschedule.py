from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models.booking import Booking, IST
from sunndari_apps.customers.models.reschedule import BookingReschedule
from sunndari_apps.customers.reschedule_listing import list_reschedules
from sunndari_apps.customers.slot_rules import slot_end_time, validate_slot
from sunndari_apps.customers.serializers.response.get_all.get_all_reschedule import RescheduleResponseGetAllSerializer
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class ArtistRescheduleView:

    def _get_artist(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def request_extract(self, params):
        artist = self._get_artist(user_id=params.user_id)
        BookingReschedule.expire_stale(booking_id=params.booking_id)
        with transaction.atomic():
            booking = Booking.objects.select_for_update().select_related('status').filter(
                booking_id=params.booking_id,
            ).first()
            if not booking or booking.artist_id != artist.artist_id:
                raise ValueError(Constants.booking_not_found)
            # Only a paid, confirmed booking that nobody has set off for yet.
            if booking.status.name != 'confirmed' or booking.on_my_way_at is not None:
                raise ValueError(Constants.reschedule_not_allowed)
            current_start = Booking.to_aware(booking.booking_date, booking.start_time)
            now = timezone.now()
            if current_start <= now:
                raise ValueError(Constants.reschedule_too_late)
            if BookingReschedule.objects.filter(booking_id=booking.booking_id, status='pending').exists():
                raise ValueError(Constants.reschedule_pending_exists)

            if (params.proposed_date, params.proposed_start_time) == (booking.booking_date, booking.start_time):
                raise ValueError(Constants.reschedule_same_slot)
            if params.proposed_date < now.astimezone(IST).date():
                raise ValueError(Constants.past_date_booking)
            proposed_start = Booking.to_aware(params.proposed_date, params.proposed_start_time)
            if proposed_start < now + timedelta(hours=Configurations.min_booking_advance_hours):
                raise ValueError(Constants.booking_too_soon)

            # The appointment keeps its length (package + add-ons), only its start moves.
            duration = datetime.combine(booking.booking_date, booking.end_time) - datetime.combine(
                booking.booking_date, booking.start_time,
            )
            proposed_end = slot_end_time(
                params.proposed_date, params.proposed_start_time, int(duration.total_seconds() // 60),
            )
            validate_slot(
                artist.artist_id, params.proposed_date, params.proposed_start_time, proposed_end,
                exclude_booking_id=booking.booking_id,
                travel_before=booking.travel_minutes_before or 0, return_buffer=booking.return_buffer_minutes or 0,
            )

            reschedule = BookingReschedule.objects.create(
                booking_id=booking.booking_id,
                requested_by_id=params.user_id,
                previous_date=booking.booking_date,
                previous_start_time=booking.start_time,
                previous_end_time=booking.end_time,
                proposed_date=params.proposed_date,
                proposed_start_time=params.proposed_start_time,
                proposed_end_time=proposed_end,
                reason=params.reason or None,
                expires_at=min(now + timedelta(hours=Configurations.reschedule_response_hours), current_start),
            )
        NotificationService.notify(
            user_id=booking.customer_id,
            title='Reschedule requested',
            message=(
                f"Your artist asked to move your booking from {booking.booking_date} to "
                f"{params.proposed_date} at {params.proposed_start_time:%H:%M}. Please accept or reject."
            ),
            type='reschedule_requested',
            booking_id=booking.booking_id,
        )
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Reschedule requested; waiting for the customer',
                data={'reschedule_id': reschedule.reschedule_id, 'expires_at': reschedule.expires_at},
            )
        )

    @Common().exception_handler
    def cancel_extract(self, params):
        artist = self._get_artist(user_id=params.user_id)
        BookingReschedule.expire_stale()
        with transaction.atomic():
            reschedule = BookingReschedule.objects.select_for_update().select_related('booking').filter(
                reschedule_id=params.reschedule_id,
            ).first()
            if not reschedule or reschedule.booking.artist_id != artist.artist_id:
                raise ValueError(Constants.reschedule_not_found)
            if reschedule.status != 'pending':
                raise ValueError(Constants.reschedule_not_pending)
            reschedule.status = 'cancelled'
            reschedule.responded_at = timezone.now()
            reschedule.save()
        NotificationService.notify(
            user_id=reschedule.booking.customer_id,
            title='Reschedule request withdrawn',
            message='Your artist withdrew the reschedule request. Your booking time is unchanged.',
            type='reschedule_cancelled',
            booking_id=reschedule.booking_id,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Reschedule request cancelled')
        )

    @Common(response_handler=RescheduleResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        artist = self._get_artist(user_id=params.user_id)
        return list_reschedules(params, artist_id=artist.artist_id)
