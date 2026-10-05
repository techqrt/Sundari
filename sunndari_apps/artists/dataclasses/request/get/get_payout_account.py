import dataclasses


@dataclasses.dataclass
class GetPayoutAccountRequest:
    values: str = ''
    user_id: int = None
    present_url: str = None
