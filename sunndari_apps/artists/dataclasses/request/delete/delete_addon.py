import dataclasses


@dataclasses.dataclass
class DeleteAddOnRequest:
    addon_id: int = None
    user_id: int = None
    present_url: str = None
