import dataclasses


@dataclasses.dataclass
class DeleteSalonAddressRequest:
    salon_address_id: int = None
    user_id: int = None
    present_url: str = None
