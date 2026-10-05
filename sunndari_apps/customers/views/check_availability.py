from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.availability_schedule import ArtistAvailabilitySchedule
from sunndari_apps.artists.models.availability_block import ArtistAvailabilityBlock
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.dataclasses.request.get.check_availability import CheckAvailabilityRequest
from sunndari_apps.customers.serializers.response.get.check_availability import AvailabilityResponseSerializer
from sunndari.constants import Constants


class CheckAvailabilityView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=AvailabilityResponseSerializer).exception_handler
    def get_extract(self, params: CheckAvailabilityRequest):
        artist = ArtistProfile.objects.filter(
            artist_id=params.artist_id, approval_status__name='approved',
        ).first()
        if not artist:
            raise ValueError(Constants.artist_not_found)

        day_of_week = params.booking_date.weekday()

        is_blocked = ArtistAvailabilityBlock.objects.filter(
            artist_id=params.artist_id, block_date=params.booking_date,
        ).exists()

        schedule = ArtistAvailabilitySchedule.objects.filter(
            artist_id=params.artist_id, day_of_week=day_of_week, is_active=True,
        ).values('start_time', 'end_time', 'location_type_id').first()

        booked_ranges = Booking.get_booked_ranges(artist_id=params.artist_id, booking_date=params.booking_date)

        data = {
            'artistId': params.artist_id,
            'bookingDate': params.booking_date,
            'dayOfWeek': day_of_week,
            'isBlocked': is_blocked,
            'workingWindow': (
                {
                    'startTime': schedule['start_time'],
                    'endTime': schedule['end_time'],
                    'locationTypeId': schedule['location_type_id'],
                } if schedule else None
            ),
            'bookedRanges': [
                {'startTime': r['start_time'], 'endTime': r['end_time']} for r in booked_ranges
            ],
            # Booked ranges widened by each booking's travel/return buffers: a new appointment's own
            # window (its start minus bufferBeforeMinutes, its end plus bufferAfterMinutes — both 0 for
            # non-Home-Visit locations) must not overlap any of these.
            'blockedRanges': [
                {'startTime': r['start_time'], 'endTime': r['end_time']}
                for r in Booking.get_blocked_ranges(artist_id=params.artist_id, booking_date=params.booking_date)
            ],
            'bufferBeforeMinutes': artist.travel_time_before_minutes,
            'bufferAfterMinutes': artist.return_buffer_minutes,
        }
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
