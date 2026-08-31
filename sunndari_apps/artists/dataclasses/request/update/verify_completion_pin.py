from dataclasses import dataclass


@dataclass
class VerifyCompletionPinRequest:
    booking_id: int
    completion_pin: int
