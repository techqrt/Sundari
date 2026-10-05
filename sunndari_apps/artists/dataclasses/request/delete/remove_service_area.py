import dataclasses


@dataclasses.dataclass
class RemoveServiceAreaRequest:
    area_id: int = None
    user_id: int = None
    present_url: str = None
