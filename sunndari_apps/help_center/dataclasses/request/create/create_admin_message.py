from dataclasses import dataclass


@dataclass
class AdminCreateMessageRequest:
    conversation_id: int
    content: str
