"""An unpaid booking must not hold the artist's slot: leaving the payment page frees it for others."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.payments.services import PaymentSettlementService
from sunndari.constants import Constants
from tests.booking_paid import pay_booking
from tests.test_user_abuse_scenarios import BOOK, MarketplaceMixin
from tests.test_customers import make_customer


class UnpaidBookingSlotTest(MarketplaceMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.first, _ = make_customer(phone_number='+919100000901')
        self.second, _ = make_customer(phone_number='+919100000902')

    def _availability(self):
        return self.second.get('/customers/artists/availability/', {
            'artist_id': self.profile.artist_id, 'booking_date': self.day.strftime('%d-%m-%y'),
        })

    def test_unpaid_booking_does_not_block_the_slot_for_others(self):
        self.assertEqual(self.book(self.first).status_code, 201)          # reached the payment page, never paid
        self.assertEqual(self.book(self.second).status_code, 201)         # the slot is still open to others

    def test_availability_ignores_unpaid_bookings_and_shows_paid_ones(self):
        booking_id = self.book(self.first).data['data']['booking_id']
        self.assertEqual(self._availability().data['data']['bookedRanges'], [])
        pay_booking(booking_id)
        self.assertEqual(len(self._availability().data['data']['bookedRanges']), 1)

    def test_paid_booking_blocks_the_slot(self):
        pay_booking(self.book(self.first).data['data']['booking_id'])
        self.assertEqual(self.book(self.second).status_code, 400)

    def test_confirmed_booking_blocks_the_slot(self):
        booking_id = self.book(self.first).data['data']['booking_id']
        Booking.objects.filter(booking_id=booking_id).update(status=Booking.objects.model._meta.get_field('status').related_model.objects.get(name='confirmed'))
        self.assertEqual(self.book(self.second).status_code, 400)

    def test_losing_the_race_is_refunded_not_double_booked(self):
        """Both reach payment; the first to pay keeps the slot, the second capture is refunded."""
        loser_id = self.book(self.first).data['data']['booking_id']
        winner_id = self.book(self.second).data['data']['booking_id']
        pay_booking(winner_id)
        payment = Payment().create(
            booking_id=loser_id, customer_id=Booking.objects.get(booking_id=loser_id).customer_id,
            artist_id=self.profile.artist_id, amount=Decimal('1500.00'), commission_amount=Decimal('0'),
            artist_payout_amount=Decimal('1500.00'), status_id=self._status('pending'),
        )
        with patch.object(PaymentSettlementService, 'refund_unapplied') as refund:
            outcome = PaymentSettlementService.apply_solo(payment_id=payment, gateway_payment_id='pay_late')
        self.assertEqual(outcome, PaymentSettlementService.SLOT_TAKEN)
        refund.assert_called_once_with([payment])
        self.assertFalse(Payment.objects.filter(booking_id=loser_id, status__name='paid').exists())

    def test_first_payment_is_applied_when_the_slot_is_still_free(self):
        booking_id = self.book(self.first).data['data']['booking_id']
        booking = Booking.objects.get(booking_id=booking_id)
        payment = Payment().create(
            booking_id=booking_id, customer_id=booking.customer_id, artist_id=self.profile.artist_id,
            amount=booking.total_amount, commission_amount=Decimal('0'),
            artist_payout_amount=booking.total_amount, status_id=self._status('pending'),
        )
        outcome = PaymentSettlementService.apply_solo(payment_id=payment, gateway_payment_id='pay_ok')
        self.assertEqual(outcome, PaymentSettlementService.APPLIED)

    def test_initiate_refuses_when_the_slot_was_taken_meanwhile(self):
        loser_id = self.book(self.first).data['data']['booking_id']
        pay_booking(self.book(self.second).data['data']['booking_id'])
        resp = self.first.post('/customers/payments/initiate/', {'booking_id': loser_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.payment_slot_taken_before_pay, resp.data['message'])
        self.assertFalse(Payment.objects.filter(booking_id=loser_id).exists())

    @staticmethod
    def _status(name):
        from sunndari_apps.core.models.payment_status import PaymentStatus
        return PaymentStatus.objects.get_or_create(name=name)[0].status_id


class ArtistSeesOnlyPaidBookingsTest(MarketplaceMixin, TestCase):
    """The artist hears about, and can open, a booking only once it has been paid for."""

    def setUp(self):
        super().setUp()
        self.customer, _ = make_customer(phone_number='+919100000911')

    def _alerts(self, booking_id):
        from sunndari_apps.notifications.models.notification import Notification
        return Notification.objects.filter(
            booking_id=booking_id, type='new_booking_alert', user_id=self.artist_user.user_id,
        ).count()

    def _artist_list(self):
        return self.artist_client.get('/artists/bookings/get_all/').data['data']['data']

    def test_unpaid_booking_is_invisible_and_silent_for_the_artist(self):
        booking_id = self.book(self.customer).data['data']['booking_id']
        self.assertEqual(self._artist_list(), [])
        self.assertEqual(self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id}).status_code, 400)
        self.assertEqual(self._alerts(booking_id), 0)

    def test_payment_makes_it_visible_and_alerts_the_artist_once(self):
        booking_id = self.book(self.customer).data['data']['booking_id']
        booking = Booking.objects.get(booking_id=booking_id)
        payment = Payment().create(
            booking_id=booking_id, customer_id=booking.customer_id, artist_id=self.profile.artist_id,
            amount=booking.total_amount, commission_amount=Decimal('0'),
            artist_payout_amount=booking.total_amount,
            status_id=UnpaidBookingSlotTest._status('pending'),
        )
        for _ in range(2):          # webhook and verify can both report the same capture
            PaymentSettlementService.apply_solo(payment_id=payment, gateway_payment_id='pay_x')
        self.assertEqual([row['bookingId'] for row in self._artist_list()], [booking_id])
        self.assertEqual(self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id}).status_code, 200)
        self.assertEqual(self._alerts(booking_id), 1)

    def test_a_refunded_slot_race_loser_never_reaches_the_artist(self):
        loser_id = self.book(self.customer).data['data']['booking_id']
        winner, _ = make_customer(phone_number='+919100000912')
        pay_booking(self.book(winner).data['data']['booking_id'])
        booking = Booking.objects.get(booking_id=loser_id)
        payment = Payment().create(
            booking_id=loser_id, customer_id=booking.customer_id, artist_id=self.profile.artist_id,
            amount=booking.total_amount, commission_amount=Decimal('0'),
            artist_payout_amount=booking.total_amount, status_id=UnpaidBookingSlotTest._status('pending'),
        )
        with patch.object(PaymentSettlementService, 'refund_unapplied'):
            PaymentSettlementService.apply_solo(payment_id=payment, gateway_payment_id='pay_late')
        self.assertEqual(self._alerts(loser_id), 0)
        self.assertNotIn(loser_id, [row['bookingId'] for row in self._artist_list()])

    def test_a_booking_cancelled_before_payment_stays_hidden(self):
        booking_id = self.book(self.customer).data['data']['booking_id']
        self.customer.put('/customers/bookings/cancel/', {'booking_id': booking_id}, format='json')
        self.assertEqual(self._artist_list(), [])

    def test_the_customer_still_sees_their_own_unpaid_booking(self):
        booking_id = self.book(self.customer).data['data']['booking_id']
        self.assertEqual(self.customer.get('/customers/bookings/get/', {'booking_id': booking_id}).status_code, 200)
