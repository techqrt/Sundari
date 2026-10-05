import dataclasses


@dataclasses.dataclass
class GetOnboardingStatusRequest:
    values: str = ''
    user_id: int = None
    present_url: str = None
