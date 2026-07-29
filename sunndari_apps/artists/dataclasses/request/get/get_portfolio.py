import dataclasses


@dataclasses.dataclass
class GetPortfolioRequest:
    portfolio_id: int = None
    values: str = ''
    user_id: int = None
    present_url: str = None
