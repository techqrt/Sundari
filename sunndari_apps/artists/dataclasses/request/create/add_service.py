import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class AddServiceRequest:
    sub_category_id: int = None
    custom_price: Decimal = None
    custom_duration_minutes: int = None
    user_id: int = None
    present_url: str = None
