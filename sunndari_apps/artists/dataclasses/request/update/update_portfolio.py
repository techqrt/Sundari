import dataclasses


@dataclasses.dataclass
class UpdatePortfolioRequest:
    portfolio_id: int = None
    caption: str = None
    sub_category_id: int = None
    is_active: bool = None
    user_id: int = None
    present_url: str = None
