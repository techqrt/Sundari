import dataclasses


@dataclasses.dataclass
class CancelRescheduleRequest:
    reschedule_id: int = None
    user_id: int = None
    present_url: str = None
