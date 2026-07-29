import dataclasses


@dataclasses.dataclass
class LocationTypeGetRequest:
    location_type_id: int = None
    values: str = ''
    user_id: int = None
    present_url: str = None
