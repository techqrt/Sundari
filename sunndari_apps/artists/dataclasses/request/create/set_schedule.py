import dataclasses


@dataclasses.dataclass
class SetScheduleRequest:
    day_of_week: int = None
    start_time: str = None
    end_time: str = None
    location_type_id: int = None
    user_id: int = None
    present_url: str = None
