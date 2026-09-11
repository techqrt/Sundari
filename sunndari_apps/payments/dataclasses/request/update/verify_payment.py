from dataclasses import dataclass


@dataclass
class VerifyPaymentRequest:
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
