from dataclasses import dataclass


@dataclass
class InitiatePaymentRequest:
    booking_id: int
    payment_type: str = 'full'
    amount: float = None
