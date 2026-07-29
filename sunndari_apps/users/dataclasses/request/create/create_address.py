import dataclasses


@dataclasses.dataclass
class CustomerAddressCreateRequest:
    address_line_1: str
    city: str
    pin_code: str
    address_line_2: str = None
    is_default: bool = False
    user_id: int = None
