from dataclasses import dataclass


@dataclass
class RequestCompletionPinRequest:
    booking_id: int
