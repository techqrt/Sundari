from dataclasses import dataclass
from datetime import date


@dataclass
class CheckAvailabilityRequest:
    artist_id: int
    booking_date: date
