from dataclasses import dataclass


@dataclass
class UpdateBookingStatusRequest:
    booking_id: int
    status: str
    reason: str = None
