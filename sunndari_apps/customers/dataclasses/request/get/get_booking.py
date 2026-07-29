from dataclasses import dataclass


@dataclass
class GetBookingRequest:
    booking_id: int
    values: str = ''
