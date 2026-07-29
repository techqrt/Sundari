from dataclasses import dataclass


@dataclass
class CancelBookingRequest:
    booking_id: int
    reason: str = None
