from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.reschedule import BookingReschedule
from sunndari_apps.customers.dataclasses.request.update.respond_reschedule import RespondRescheduleRequest
from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
from sunndari_apps.customers.reschedule_listing import list_reschedules
from sunndari_apps.customers.slot_rules import validate_slot
from sunndari_apps.customers.serializers.response.get_all.get_all_reschedule import RescheduleResponseGetAllSerializer
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class CustomerRescheduleView:

    @Common().exception_handler
    def respond_extract(self, params: RespondRescheduleRequest):
        BookingReschedule.expire_stale()
        with transaction.atomic():
            reschedule = BookingReschedule.objects.select_for_update().select_related('booking').filter(
                reschedule_id=params.reschedule_id,
            ).first()
            if not reschedule or reschedule.booking.customer_id != params.user_id:
                raise ValueError(Constants.reschedule_not_found)
            if reschedule.status != 'pending':
                raise ValueError(Constants.reschedule_not_pending)

            booking = Booking.objects.select_for_update().select_related('status').get(
                booking_id=reschedule.booking_id,
            )
            if params.decision == 'accepted':
                # Everything is re-checked now, not trusted from request time: the booking
                # may have moved on, and the proposed slot may have been taken meanwhile.
                if booking.status.name != 'confirmed' or booking.on_my_way_at is not None:
                    raise ValueError(Constants.reschedule_not_allowed)
                if Booking.to_aware(reschedule.proposed_date, reschedule.proposed_start_time) <= timezone.now():
                    raise ValueError(Constants.booking_too_soon)
                validate_slot(
                    booking.artist_id, reschedule.proposed_date, reschedule.proposed_start_time,
                    reschedule.proposed_end_time, exclude_booking_id=booking.booking_id,
                    travel_before=booking.travel_minutes_before or 0,
                    return_buffer=booking.return_buffer_minutes or 0,
                )
                Booking.reschedule_slot(
                    booking_id=booking.booking_id,
                    booking_date=reschedule.proposed_date,
                    start_time=reschedule.proposed_start_time,
                    end_time=reschedule.proposed_end_time,
                )
            reschedule.status = params.decision
            reschedule.responded_at = timezone.now()
            reschedule.save()

        artist = ArtistProfile.get(artist_id=booking.artist_id)
        if artist:
            accepted = params.decision == 'accepted'
            NotificationService.notify(
                user_id=artist['user_id'],
                title='Reschedule accepted' if accepted else 'Reschedule rejected',
                message=(
                    f"The customer accepted the new time ({reschedule.proposed_date} "
                    f"{reschedule.proposed_start_time:%H:%M})." if accepted
                    else 'The customer rejected the new time. The booking stays as originally scheduled.'
                ),
                type=f'reschedule_{params.decision}',
                booking_id=booking.booking_id,
            )
        if params.decision == 'accepted':
            BookingFirebaseUtils.sync_booking(booking_id=booking.booking_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=f'Reschedule {params.decision}')
        )

    @Common(response_handler=RescheduleResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        return list_reschedules(params, customer_id=params.user_id)
