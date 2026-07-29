from dataclasses import dataclass
from datetime import date, time


@dataclass
class CreateBookingRequest:
    artist_id: int
    package_id: int
    location_type_id: int
    booking_date: date
    start_time: time
    address_id: int = None
    notes: str = None
