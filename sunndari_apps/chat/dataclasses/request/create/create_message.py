from dataclasses import dataclass


@dataclass
class CreateMessageRequest:
    booking_id: int
    content: str
