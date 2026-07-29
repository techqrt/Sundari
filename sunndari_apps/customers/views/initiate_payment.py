from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.payment import Payment
from sunndari_apps.customers.dataclasses.request.create.initiate_payment import InitiatePaymentRequest
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
            raise ValueError(Constants.update_not_allowed)

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
        payment = Payment.get(payment_id=payment_id)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message='Payment initiated. Complete payment using the returned order reference.',
                data={
                    'payment_id': payment_id,
                    'gateway_order_id': payment['gateway_order_id'],
                    'amount': str(amount),
                },
            )
        )
