import dataclasses


@dataclasses.dataclass
class ReplyReviewRequest:
    review_id: int = None
    reply: str = None
    user_id: int = None
    present_url: str = None
