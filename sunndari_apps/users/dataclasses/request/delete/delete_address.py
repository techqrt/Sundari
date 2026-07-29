import dataclasses


@dataclasses.dataclass
class CustomerAddressDeleteRequest:
    address_id: int
    user_id: int = None
