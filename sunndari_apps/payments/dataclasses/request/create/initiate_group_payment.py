from dataclasses import dataclass


@dataclass
class InitiateGroupPaymentRequest:
    booking_ids: list
    redemption_tier_id: int = None
