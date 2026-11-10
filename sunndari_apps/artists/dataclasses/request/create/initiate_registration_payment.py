import dataclasses


@dataclasses.dataclass
class InitiateRegistrationPaymentRequest:
    promo_code: str = None
    user_id: int = None
    present_url: str = None
