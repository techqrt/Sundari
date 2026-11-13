import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class CreateSalonAddressRequest:
    name: str = None
    address_line_1: str = None
    address_line_2: str = None
    city: str = None
    pin_code: str = None
    latitude: Decimal = None
    longitude: Decimal = None
    user_id: int = None
    present_url: str = None
