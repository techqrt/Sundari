from dataclasses import dataclass


@dataclass
class ArrivedRequest:
    booking_id: int
    booking_otp: int = None   # no longer used: arrival is confirmed without the Booking OTP
