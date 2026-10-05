import dataclasses


@dataclasses.dataclass
class SetSpecialitiesRequest:
    sub_category_ids: list = None
    user_id: int = None
    present_url: str = None
