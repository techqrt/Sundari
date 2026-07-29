from dataclasses import dataclass


@dataclass
class GetReviewRequest:
    review_id: int
    values: str = ''
