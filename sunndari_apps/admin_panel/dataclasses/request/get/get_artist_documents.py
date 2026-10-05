from dataclasses import dataclass


@dataclass
class GetArtistDocumentsRequest:
    artist_id: int
    user_id: int = None
    present_url: str = None
