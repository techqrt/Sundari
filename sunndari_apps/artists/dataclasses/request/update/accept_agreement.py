import dataclasses


@dataclasses.dataclass
class AcceptAgreementRequest:
    user_id: int = None
    present_url: str = None
