from dataclasses import dataclass


@dataclass
class GetConversationRequest:
    booking_id: int
    values: str = ''
