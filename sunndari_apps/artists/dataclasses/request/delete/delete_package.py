import dataclasses


@dataclasses.dataclass
class DeletePackageRequest:
    package_id: int = None
    user_id: int = None
    present_url: str = None
