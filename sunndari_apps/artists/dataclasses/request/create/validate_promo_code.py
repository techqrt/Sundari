import dataclasses


@dataclasses.dataclass
class ValidatePromoCodeRequest:
    promo_code: str
    user_id: int = None
    present_url: str = None
