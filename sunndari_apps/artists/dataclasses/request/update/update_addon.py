import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class UpdateAddOnRequest:
    addon_id: int = None
    name: str = None
    price: Decimal = None
    duration_minutes: int = None
    description: str = None
    is_active: bool = None
    package_ids: list = None
    user_id: int = None
    present_url: str = None
