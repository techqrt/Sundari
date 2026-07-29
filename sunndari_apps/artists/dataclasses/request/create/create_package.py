import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class CreatePackageRequest:
    sub_category_id: int = None
    name: str = None
    price: Decimal = None
    duration_minutes: int = None
    description: str = None
    inclusions: list = dataclasses.field(default_factory=list)
    user_id: int = None
    present_url: str = None
