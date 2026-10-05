import dataclasses


@dataclasses.dataclass
class UploadPackagePhotoRequest:
    package_id: int = None
    user_id: int = None
    present_url: str = None
