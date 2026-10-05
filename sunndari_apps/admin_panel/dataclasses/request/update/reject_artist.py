from dataclasses import dataclass


@dataclass
class RejectArtistRequest:
    artist_id: int
    reason: str = None
    user_id: int = None
