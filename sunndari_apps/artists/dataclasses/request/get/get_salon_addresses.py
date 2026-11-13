import dataclasses


@dataclasses.dataclass
class GetSalonAddressesRequest:
    values: str = ''
    user_id: int = None
    present_url: str = None
