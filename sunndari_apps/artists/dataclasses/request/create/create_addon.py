import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class CreateAddOnRequest:
    name: str = None
    price: Decimal = None
    duration_minutes: int = 0
    description: str = None
    is_active: bool = True
    package_ids: list = dataclasses.field(default_factory=list)
    user_id: int = None
    present_url: str = None
