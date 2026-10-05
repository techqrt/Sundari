from datetime import datetime, timedelta

from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.availability_block import ArtistAvailabilityBlock
from sunndari_apps.artists.models.availability_schedule import ArtistAvailabilitySchedule
from sunndari_apps.customers.models.booking import Booking
from sunndari.constants import Constants


def slot_end_time(booking_date, start_time, duration_minutes: int):
    """End time of a slot; a slot may not run past midnight."""
    start_dt = datetime.combine(booking_date, start_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    if end_dt.date() != booking_date:
        raise ValueError(Constants.slot_unavailable)
    return end_dt.time()


def minutes_of(moment) -> int:
    return moment.hour * 60 + moment.minute


def buffers_for(location_name, artist) -> tuple:
    """(travel_before, return_buffer) in minutes that apply to a booking at this location.
    Only Home Visits involve travelling; a studio appointment blocks no extra time."""
    if location_name == 'Home Visit':
        return artist.travel_time_before_minutes or 0, artist.return_buffer_minutes or 0
    return 0, 0


def validate_slot(
    artist_id: int, booking_date, start_time, end_time, exclude_booking_id: int = None,
    travel_before: int = 0, return_buffer: int = 0,
) -> None:
    """The single definition of "this artist can take an appointment here", shared by new
    bookings and reschedules: not a blocked date, inside the artist's working window for
    that weekday, and not overlapping another active booking.

    Must be called inside transaction.atomic(): it locks the artist's active bookings for
    the day (select_for_update) so two concurrent requests can't both claim the slot."""
    if ArtistAvailabilityBlock.objects.filter(artist_id=artist_id, block_date=booking_date).exists():
        raise ValueError(Constants.slot_unavailable)

    schedule = ArtistAvailabilitySchedule.objects.filter(
        artist_id=artist_id, day_of_week=booking_date.weekday(), is_active=True,
    ).first()
    if not schedule or schedule.start_time > start_time or end_time > schedule.end_time:
        raise ValueError(Constants.slot_unavailable)

    # Lock the artist's own row first. Locking only their existing bookings (below) locks nothing when
    # the day is still empty, so two simultaneous first requests would both pass. Every booking for
    # one artist now queues behind this row lock (effective on PostgreSQL; SQLite serialises writers).
    ArtistProfile.objects.select_for_update().filter(artist_id=artist_id).first()
    locked = Booking.objects.select_for_update().filter(
        artist_id=artist_id,
        booking_date=booking_date,
        status__name__in=Booking.ACTIVE_STATUSES,
    )
    if exclude_booking_id:
        locked = locked.exclude(booking_id=exclude_booking_id)
    # Each appointment occupies [start - travel_before, end + return_buffer]. Two bookings conflict
    # when those occupied windows overlap, so back-to-back appointments need room for the earlier
    # one's return trip plus the later one's travel. Bookings made before buffers existed carry no
    # snapshot (None) and count as zero. Same-day comparison only, like the rest of the slot rules.
    new_from = minutes_of(start_time) - (travel_before or 0)
    new_to = minutes_of(end_time) + (return_buffer or 0)
    for existing in list(locked):
        existing_from = minutes_of(existing.start_time) - (existing.travel_minutes_before or 0)
        existing_to = minutes_of(existing.end_time) + (existing.return_buffer_minutes or 0)
        if existing_from < new_to and existing_to > new_from:
            raise ValueError(Constants.double_booking)
