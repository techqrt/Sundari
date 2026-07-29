import dataclasses


@dataclasses.dataclass
class RemoveServiceRequest:
    sub_category_id: int = None
    user_id: int = None
    present_url: str = None
