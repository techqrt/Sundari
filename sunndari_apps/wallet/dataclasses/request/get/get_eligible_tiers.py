from dataclasses import dataclass


@dataclass
class GetEligibleTiersRequest:
    booking_id: int
    amount: float = None
