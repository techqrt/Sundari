from dataclasses import dataclass


@dataclass
class GetBookingRequest:
    booking_id: int
    values: str = ''
    filter_key: str = ''
    filter_value: str = ''
