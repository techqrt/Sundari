import dataclasses


@dataclasses.dataclass
class CreatePortfolioRequest:
    media_type: str = None
    sub_category_id: int = None
    caption: str = None
    user_id: int = None
    present_url: str = None
