import dataclasses


@dataclasses.dataclass
class ReorderPortfolioRequest:
    portfolio_ids: list = None
    user_id: int = None
    present_url: str = None
