from dataclasses import dataclass


@dataclass
class GetPaymentRequest:
    payment_id: int
    values: str = ''
