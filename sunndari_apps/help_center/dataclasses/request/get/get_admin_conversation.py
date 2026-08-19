from dataclasses import dataclass


@dataclass
class AdminGetConversationRequest:
    conversation_id: int
    values: str = ''
