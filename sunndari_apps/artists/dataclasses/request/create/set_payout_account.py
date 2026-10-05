import dataclasses


@dataclasses.dataclass
class SetPayoutAccountRequest:
    account_holder_name: str = None
    bank_account_number: str = None
    ifsc_code: str = None
    upi_id: str = None
    user_id: int = None
    present_url: str = None
