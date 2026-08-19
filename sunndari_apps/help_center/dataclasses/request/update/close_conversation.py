from dataclasses import dataclass


@dataclass
class CloseConversationRequest:
    conversation_id: int
