from dataclasses import dataclass


@dataclass
class CreateMessageRequest:
    content: str
    subject: str = None
