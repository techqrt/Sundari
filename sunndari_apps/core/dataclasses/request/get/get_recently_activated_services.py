import dataclasses


@dataclasses.dataclass
class RecentlyActivatedServicesRequest:
    user_id: int = None
    present_url: str = None
