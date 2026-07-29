import dataclasses


@dataclasses.dataclass
class ArtistProfileUpdateRequest:
    bio: str = None
    years_experience: int = None
    city: str = None
    service_radius_km: int = None
    user_id: int = None
    present_url: str = None
