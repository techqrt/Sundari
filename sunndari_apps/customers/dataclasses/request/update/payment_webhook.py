from dataclasses import dataclass


@dataclass
class PaymentWebhookRequest:
    gateway_order_id: str
    gateway_payment_id: str
    status: str
    reason: str = None
