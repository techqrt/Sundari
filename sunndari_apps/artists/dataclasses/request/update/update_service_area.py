import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class UpdateServiceAreaRequest:
    area_id: int = None
    city: str = None
    travel_charge_type: str = None
    charge_amount: Decimal = None
    is_active: bool = None
    user_id: int = None
    present_url: str = None
