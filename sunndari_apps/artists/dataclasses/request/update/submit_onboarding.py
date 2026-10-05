import dataclasses


@dataclasses.dataclass
class SubmitOnboardingRequest:
    user_id: int = None
    present_url: str = None
