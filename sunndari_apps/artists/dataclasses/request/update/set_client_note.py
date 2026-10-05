import dataclasses


@dataclasses.dataclass
class SetClientNoteRequest:
    customer_id: int = None
    note: str = None
    user_id: int = None
    present_url: str = None
