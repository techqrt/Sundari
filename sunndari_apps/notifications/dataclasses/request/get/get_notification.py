from dataclasses import dataclass


@dataclass
class GetNotificationRequest:
    notification_id: int
    values: str = ''
