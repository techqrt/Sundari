from dataclasses import dataclass


@dataclass
class MarkReadRequest:
    notification_id: int
