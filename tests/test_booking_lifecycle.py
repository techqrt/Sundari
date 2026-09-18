"""End-to-end regression test for the full booking-execution lifecycle:

    customer books -> Booking OTP issued -> artist accepts -> on my way (2h window)
    -> arrived (Booking OTP verified, Start PIN issued) -> start PIN verified
    (in_progress, Completion PIN issued) -> completion PIN verified (completed)

Walks every step through the real HTTP APIs (never touching internal booking
fields directly except to read the Booking OTP, which is deliberately never
exposed through any API — the real artist would receive it via SMS/notification).
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.customers.models import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.artists.models import ArtistAvailabilitySchedule
from sunndari_apps.wallet.models import CustomerWallet, CoinTransaction, CoinConfig

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type,
    make_package, make_location_preference, seed_booking_statuses, seed_payment_statuses, IST,
)


class FullBookingLifecycleTest(TestCase):

    def setUp(self):
        # Pinned explicitly rather than relying on CoinConfig's model default, so this
        # test's cashback assertion stays stable regardless of what that default is.
        CoinConfig.objects.create(coin_value_rupees='0.10')
        # A booking can't be confirmed without a verified payment (see Stage 5) — this
        # E2E test walks the real /initiate/ + /verify/ endpoints too, so RazorpayGateway
        # is mocked the same way tests/test_payments.py does, keeping it hermetic.
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_client.utility.verify_payment_signature.return_value = None
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def _pay_for_booking(self, customer_client, booking_id):
        seed_payment_statuses()
        init_resp = customer_client.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json')
        self.assertEqual(init_resp.status_code, 201)
        order_id = init_resp.data['data']['gateway_order_id']
        amount_paise = init_resp.data['data']['amount']
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_test_lifecycle', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        verify_resp = customer_client.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_lifecycle', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(verify_resp.status_code, 200)

    def test_full_lifecycle_end_to_end(self):
        seed_booking_statuses()
        customer_client, customer = make_customer(phone_number='+919000000900')
        artist_client, artist_user, profile = make_artist(phone_number='+919000000901')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, duration=30)
        location_type = make_location_type()
        make_location_preference(profile, location_type)

        # Safely past the 2h-minimum-advance rule at creation time — the on-my-way
        # window (needs the booking within 2h of now) is brought into range afterward
        # by directly advancing the booking's own scheduled time, rather than racing
        # a wall-clock boundary that elapsed test-execution time would make flaky.
        booking_start = (timezone.now() + timedelta(hours=3)).astimezone(IST)
        ArtistAvailabilitySchedule.objects.create(
            artist=profile, day_of_week=booking_start.weekday(),
            start_time='00:00:00', end_time='23:59:00',
        )

        # ── Customer books the artist ──────────────────────────────────────
        create_resp = customer_client.post('/customers/bookings/create/', {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_start.strftime('%d-%m-%y'),
            'start_time': booking_start.strftime('%H:%M:%S'),
        }, format='json')
        self.assertEqual(create_resp.status_code, 201)
        booking_id = create_resp.data['data']['booking_id']

        # ── Booking OTP issued to the artist ───────────────────────────────
        booking = Booking.objects.get(booking_id=booking_id)
        self.assertIsNotNone(booking.booking_otp)
        booking_otp = booking.booking_otp
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='new_booking_alert', user_id=artist_user.user_id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='booking_otp_issued', user_id=artist_user.user_id).exists()
        )

        # ── Customer pays — required before the artist can confirm ─────────
        self._pay_for_booking(customer_client, booking_id)

        # ── Artist accepts ──────────────────────────────────────────────────
        accept_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(accept_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'confirmed')
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='booking_confirmed', user_id=customer.user_id).exists()
        )

        # ── On My Way (within the 2h window) ───────────────────────────────
        # Advance the booking's own scheduled time to bring it within the on-my-way
        # window, simulating that the appointment is now imminent.
        near_start = (timezone.now() + timedelta(hours=1)).astimezone(IST)
        booking.booking_date = near_start.date()
        booking.start_time = near_start.time()
        booking.save()

        on_my_way_resp = artist_client.put('/artists/bookings/on_my_way/', {'booking_id': booking_id}, format='json')
        self.assertEqual(on_my_way_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.on_my_way_at)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='artist_on_the_way', user_id=customer.user_id).exists()
        )

        # ── Arrived (Booking OTP verified, Start PIN minted) ───────────────
        arrived_resp = artist_client.put('/artists/bookings/arrived/', {
            'booking_id': booking_id, 'booking_otp': booking_otp,
        }, format='json')
        self.assertEqual(arrived_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.arrived_at)
        self.assertIsNotNone(booking.booking_otp_verified_at)
        self.assertIsNone(booking.booking_otp)
        self.assertIsNotNone(booking.start_service_pin)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='artist_arrived', user_id=customer.user_id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='start_pin_ready', user_id=customer.user_id).exists()
        )

        # ── Customer retrieves the Start PIN and shares it with the artist ─
        start_pin_resp = customer_client.get('/customers/bookings/start_pin/', {'booking_id': booking_id})
        self.assertEqual(start_pin_resp.status_code, 200)
        start_pin = start_pin_resp.data['data']['startServicePin']
        self.assertEqual(start_pin, booking.start_service_pin)

        # ── Artist verifies the Start PIN — service begins ─────────────────
        verify_start_resp = artist_client.put('/artists/bookings/start_pin/verify/', {
            'booking_id': booking_id, 'start_service_pin': start_pin,
        }, format='json')
        self.assertEqual(verify_start_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')
        self.assertIsNotNone(booking.service_started_at)
        self.assertIsNone(booking.start_service_pin)
        self.assertIsNotNone(booking.completion_pin)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='service_started', user_id=customer.user_id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='completion_pin_ready', user_id=customer.user_id).exists()
        )

        # ── Customer retrieves the Completion PIN and shares it ────────────
        completion_pin_resp = customer_client.get('/customers/bookings/completion_pin/', {'booking_id': booking_id})
        self.assertEqual(completion_pin_resp.status_code, 200)
        completion_pin = completion_pin_resp.data['data']['completionPin']
        self.assertEqual(completion_pin, booking.completion_pin)

        # ── Artist verifies the Completion PIN — service completed ────────
        verify_completion_resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
            'booking_id': booking_id, 'completion_pin': completion_pin,
        }, format='json')
        self.assertEqual(verify_completion_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'completed')
        self.assertIsNotNone(booking.service_completed_at)
        self.assertIsNone(booking.completion_pin)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='booking_completed', user_id=customer.user_id).exists()
        )

        # ── Cashback is credited to the customer's wallet on completion ────
        # Default package price is ₹1500; at the default 10% cashback rate and ₹0.10
        # coin value, cashback coins == the price's numeric value (₹150 / ₹0.10).
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 1500)
        cashback_txn = CoinTransaction.objects.get(
            wallet=wallet, booking_id=booking_id, transaction_type='CASHBACK',
        )
        self.assertEqual(cashback_txn.coins, 1500)
        self.assertEqual(cashback_txn.remaining_coins, 1500)
        self.assertIsNotNone(cashback_txn.expires_at)

        # ── Chat is closed once the booking completes ──────────────────────
        message_resp = customer_client.post('/chat/messages/create/', {
            'booking_id': booking_id, 'content': 'too late',
        }, format='json')
        self.assertEqual(message_resp.status_code, 400)

    def test_rejected_booking_voids_booking_otp_and_blocks_lifecycle(self):
        seed_booking_statuses()
        customer_client, customer = make_customer(phone_number='+919000000910')
        artist_client, artist_user, profile = make_artist(phone_number='+919000000911')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, duration=30)
        location_type = make_location_type()
        make_location_preference(profile, location_type)

        booking_start = (timezone.now() + timedelta(hours=3)).astimezone(IST)
        ArtistAvailabilitySchedule.objects.create(
            artist=profile, day_of_week=booking_start.weekday(),
            start_time='00:00:00', end_time='23:59:00',
        )

        create_resp = customer_client.post('/customers/bookings/create/', {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_start.strftime('%d-%m-%y'),
            'start_time': booking_start.strftime('%H:%M:%S'),
        }, format='json')
        booking_id = create_resp.data['data']['booking_id']
        booking = Booking.objects.get(booking_id=booking_id)
        booking_otp = booking.booking_otp

        reject_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking_id, 'status': 'cancelled',
        }, format='json')
        self.assertEqual(reject_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertEqual(booking.cancelled_by, 'artist')
        self.assertIsNone(booking.booking_otp)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking_id, type='booking_cancelled', user_id=customer.user_id).exists()
        )

        # A rejected booking can never reach on-my-way, regardless of the (voided) OTP.
        on_my_way_resp = artist_client.put('/artists/bookings/on_my_way/', {'booking_id': booking_id}, format='json')
        self.assertEqual(on_my_way_resp.status_code, 400)
        arrived_resp = artist_client.put('/artists/bookings/arrived/', {
            'booking_id': booking_id, 'booking_otp': booking_otp,
        }, format='json')
        self.assertEqual(arrived_resp.status_code, 400)
