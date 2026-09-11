import razorpay
from sunndari.config import Configurations


class RazorpayGateway:
    """Lazy singleton Razorpay SDK client — mirrors FirebaseUtils's lazy-init pattern
    (sunndari_apps/notifications/firebase_utils.py). Unlike Firebase, Client()
    construction itself makes no network call, so this is safe to build even under the
    test runner; individual SDK calls (order.create, payment.fetch,
    utility.verify_payment_signature) are what call out over the network, and those are
    what call sites/tests mock."""

    _client = None

    @classmethod
    def get_client(cls) -> razorpay.Client:
        if cls._client is None:
            cls._client = razorpay.Client(auth=(Configurations.razorpay_key_id, Configurations.razorpay_key_secret))
        return cls._client
