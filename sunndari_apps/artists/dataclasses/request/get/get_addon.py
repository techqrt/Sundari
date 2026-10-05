import dataclasses


@dataclasses.dataclass
class GetAddOnRequest:
    addon_id: int = None
    values: str = ''
    user_id: int = None
    present_url: str = None
