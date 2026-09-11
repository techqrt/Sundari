import razorpay
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.payments.gateway import RazorpayGateway
from sunndari_apps.payments.dataclasses.request.create.initiate_payment import InitiatePaymentRequest
from sunndari.constants import Constants


class InitiatePaymentView:

    @Common().exception_handler
    def initiate_extract(self, params: InitiatePaymentRequest):
        booking = Booking.get(booking_id=params.booking_id)
        if not booking or booking['customer_id'] != params.user_id:
            raise ValueError(Constants.booking_not_found)

        status_name = BookingStatus.objects.filter(
            status_id=booking['status_id'],
        ).values_list('name', flat=True).first()
        if status_name not in Booking.ACTIVE_STATUSES:
            raise ValueError(f"Payment cannot be initiated — booking is '{status_name}'.")

        already_paid = Payment.total_paid_for_booking(booking_id=params.booking_id)
        remaining_due = booking['total_amount'] - already_paid
        if remaining_due <= 0:
            raise ValueError(Constants.payment_already_completed)

        amount = params.amount if params.amount is not None else remaining_due
        if amount <= 0 or amount > remaining_due:
            raise ValueError(Constants.invalid_payment_amount)

        artist = ArtistProfile.objects.filter(artist_id=booking['artist_id']).first()
        commission_amount = round(amount * artist.commission_rate / 100, 2)
        artist_payout_amount = amount - commission_amount

        pending_status = PaymentStatus.objects.filter(name='pending').first()
        payment_id = Payment().create(
            booking_id=params.booking_id,
            customer_id=params.user_id,
            artist_id=booking['artist_id'],
            amount=amount,
            commission_amount=commission_amount,
            artist_payout_amount=artist_payout_amount,
            status_id=pending_status.status_id,
            payment_type=params.payment_type,
        )

        # Razorpay amounts are in the smallest currency unit (paise for INR), never a
        # client-supplied figure — always derived from the same server-authoritative
        # `amount` computed above.
        amount_in_paise = int(round(amount * 100))
        try:
            razorpay_order = RazorpayGateway.get_client().order.create(data={
                'amount': amount_in_paise,
                'currency': Configurations.razorpay_currency,
                'receipt': f'payment_{payment_id}',
            })
        except (razorpay.errors.BadRequestError, razorpay.errors.ServerError, razorpay.errors.GatewayError) as e:
            failed_status = PaymentStatus.objects.filter(name='failed').first()
            Payment.mark_failed(payment_id=payment_id, status_id=failed_status.status_id, failure_reason=str(e)[:300])
            raise ValueError('Unable to initiate payment with the payment gateway. Please try again.')

        Payment.set_gateway_order(payment_id=payment_id, gateway='razorpay', gateway_order_id=razorpay_order['id'])
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Payment initiated. Complete payment using the returned order reference.',
                data={
                    'payment_id': payment_id,
                    'gateway_order_id': razorpay_order['id'],
                    'razorpay_key_id': Configurations.razorpay_key_id,
                    'amount': amount_in_paise,
                    'currency': Configurations.razorpay_currency,
                },
            )
        )
