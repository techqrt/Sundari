import dataclasses


@dataclasses.dataclass
class UserProfileUpdateRequest:
    name: str = None
    email: str = None
    phone_number: str = None
    fcm_token: str = None
    user_id: int = None
