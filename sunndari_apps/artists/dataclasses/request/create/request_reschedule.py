import dataclasses
from datetime import date, time


@dataclasses.dataclass
class RequestRescheduleRequest:
    booking_id: int = None
    proposed_date: date = None
    proposed_start_time: time = None
    reason: str = None
    user_id: int = None
    present_url: str = None
