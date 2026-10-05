import dataclasses


@dataclasses.dataclass
class SetAcceptingBookingsRequest:
    is_accepting_bookings: bool = None
    user_id: int = None
    present_url: str = None
