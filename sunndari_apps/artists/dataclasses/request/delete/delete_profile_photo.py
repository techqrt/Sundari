import dataclasses


@dataclasses.dataclass
class DeleteProfilePhotoRequest:
    kind: str = None
    user_id: int = None
    present_url: str = None
