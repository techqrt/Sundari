import dataclasses


@dataclasses.dataclass
class AddBlockRequest:
    block_date: str = None
    note: str = None
    user_id: int = None
    present_url: str = None
