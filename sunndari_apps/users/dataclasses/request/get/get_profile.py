import dataclasses


@dataclasses.dataclass
class UserProfileGetRequest:
    profile_user_id: int = None
    values: str = ''
    user_id: int = None
    present_url: str = None
