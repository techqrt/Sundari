import dataclasses


@dataclasses.dataclass
class GetShareLinkRequest:
    user_id: int = None
    present_url: str = None
