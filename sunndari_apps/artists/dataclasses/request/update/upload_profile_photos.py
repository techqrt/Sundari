import dataclasses


@dataclasses.dataclass
class UploadProfilePhotosRequest:
    user_id: int = None
    present_url: str = None
