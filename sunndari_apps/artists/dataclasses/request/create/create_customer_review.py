import dataclasses


@dataclasses.dataclass
class CreateCustomerReviewRequest:
    booking_id: int = None
    rating: int = None
    comment: str = None
    user_id: int = None
    present_url: str = None
