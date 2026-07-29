import dataclasses


@dataclasses.dataclass
class CustomerAddressGetRequest:
    address_id: int
    values: str = ''
    user_id: int = None
    present_url: str = None
