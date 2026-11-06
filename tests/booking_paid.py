from decimal import Decimal

from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.payments.models import Payment


def pay_booking(booking_id: int, customer_id: int = None, artist_id: int = None):
    """Marks a booking paid, directly. An unpaid pending booking no longer holds its artist's slot, so a test
    about slot conflicts must pay for the booking it expects to block. Pass `response` from a booking POST via
    `pay_response` when only the HTTP response is at hand."""
    from sunndari_apps.customers.models.booking import Booking
    booking = Booking.objects.get(booking_id=booking_id)
    paid, _ = PaymentStatus.objects.get_or_create(name='paid')
    Payment().create(
        booking_id=booking.booking_id, customer_id=booking.customer_id, artist_id=booking.artist_id,
        amount=booking.total_amount, commission_amount=Decimal('0'), artist_payout_amount=booking.total_amount,
        status_id=paid.status_id,
    )


def pay_response(response):
    """Pays for the booking a successful create-booking response made; returns the response unchanged."""
    if response.status_code == 201:
        pay_booking(response.data['data']['booking_id'])
    return response
