from dataclasses import dataclass


@dataclass
class ArrivedRequest:
    booking_id: int
    booking_otp: int
