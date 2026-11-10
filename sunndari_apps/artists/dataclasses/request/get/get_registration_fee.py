import dataclasses


@dataclasses.dataclass
class GetRegistrationFeeRequest:
    values: str = ''
    user_id: int = None
    present_url: str = None
