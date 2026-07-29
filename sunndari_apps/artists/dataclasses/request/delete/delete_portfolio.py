import dataclasses


@dataclasses.dataclass
class DeletePortfolioRequest:
    portfolio_id: int = None
    user_id: int = None
    present_url: str = None
