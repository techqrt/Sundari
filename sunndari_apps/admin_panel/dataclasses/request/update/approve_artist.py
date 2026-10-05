from dataclasses import dataclass


@dataclass
class ApproveArtistRequest:
    artist_id: int
    message: str = ''
    user_id: int = None
