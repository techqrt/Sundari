import dataclasses


@dataclasses.dataclass
class RemoveScheduleRequest:
    day_of_week: int = None
    user_id: int = None
    present_url: str = None
