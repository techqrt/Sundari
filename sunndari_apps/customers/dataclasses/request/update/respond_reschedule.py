from dataclasses import dataclass


@dataclass
class RespondRescheduleRequest:
    reschedule_id: int
    decision: str
    user_id: int = None
