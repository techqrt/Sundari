from dataclasses import dataclass


@dataclass
class CreateReviewRequest:
    booking_id: int
    rating: int
    comment: str = None
