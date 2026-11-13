import dataclasses
from decimal import Decimal


@dataclasses.dataclass
class UpdateSalonAddressRequest:
    salon_address_id: int = None
    name: str = None
    address_line_1: str = None
    address_line_2: str = None
    city: str = None
    pin_code: str = None
    latitude: Decimal = None
    longitude: Decimal = None
    # The fields the caller actually sent. address_line_2 can be cleared with null or "", so None alone cannot tell
    # "leave it" from "clear it".
    provided: tuple = ()
    user_id: int = None
    present_url: str = None
