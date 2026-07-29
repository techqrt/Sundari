import dataclasses


@dataclasses.dataclass
class CustomerAddressUpdateRequest:
    address_id: int
    address_line_1: str = None
    address_line_2: str = None
    city: str = None
    pin_code: str = None
    is_default: bool = None
    user_id: int = None
