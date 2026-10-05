import dataclasses


@dataclasses.dataclass
class ArtistProfileUpdateRequest:
    display_name: str = None
    travel_time_before_minutes: int = None
    return_buffer_minutes: int = None
    date_of_birth: object = None
    instagram_url: str = None
    profile_type: str = None
    bio: str = None
    years_experience: int = None
    city: str = None
    service_radius_km: int = None
    base_address_id: int = None
    user_id: int = None
    present_url: str = None
