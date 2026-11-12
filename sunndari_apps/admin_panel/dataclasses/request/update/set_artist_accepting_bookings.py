from dataclasses import dataclass


@dataclass
class SetArtistAcceptingBookingsRequest:
    artist_id: int
    is_accepting_bookings: bool
    user_id: int = None
