from dataclasses import dataclass


@dataclass
class VerifyStartPinRequest:
    booking_id: int
    start_service_pin: int
