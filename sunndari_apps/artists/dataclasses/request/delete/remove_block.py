import dataclasses


@dataclasses.dataclass
class RemoveBlockRequest:
    block_date: str = None
    user_id: int = None
    present_url: str = None
