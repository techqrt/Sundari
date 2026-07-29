import dataclasses


@dataclasses.dataclass
class RemoveLocationRequest:
    location_type_id: int = None
    user_id: int = None
    present_url: str = None
