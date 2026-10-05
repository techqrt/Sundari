import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class AddServiceAreaRequest:
    city: str = None
    travel_charge_type: str = None
    charge_amount: Decimal = None
    user_id: int = None
    present_url: str = None
