import razorpay
from unittest.mock import patch, MagicMock
from django.test import TestCase

from sunndari.config import Configurations
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.wallet.models import RedemptionTier, CustomerWallet, CoinTransaction

from tests.test_customers import (
    make_customer, make_artist, make_client, make_sub_category, make_location_type,
    make_package, make_booking, next_weekday, seed_payment_statuses,
)
from sunndari_apps.authentication.models import User


# ─── Payment ───────────────────────────────────────────────────────────────────

class PaymentTest(TestCase):
    initiate_url = '/customers/payments/initiate/'
    get_all_url = '/customers/payments/get_all/'
    payment_types_url = '/customers/payments/payment_types/'

    def setUp(self):
        # /initiate/ now calls the real Razorpay SDK — mock RazorpayGateway.get_client()
        # so tests stay hermetic (no network call, no real credentials needed). Each order
        # gets a distinct id derived from the receipt (which embeds payment_id), matching
        # the DB's unique constraint on gateway_order_id.
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}",
            'amount': data['amount'],
            'currency': data['currency'],
            'status': 'created',
        }
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def test_get_payment_types_returns_full_advance_balance(self):
        client, _ = make_customer(phone_number='+919000000290')
        resp = client.get(self.payment_types_url)
        self.assertEqual(resp.status_code, 200)
        values = {item['value'] for item in resp.data['data']}
        self.assertEqual(values, {'full', 'advance', 'balance'})

    def _make_booking(self, customer_phone='+919000000280', artist_phone='+919000000281', price=1500):
        client, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return client, customer, profile, booking

    def test_initiate_payment_full_amount(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking()
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('gateway_order_id', resp.data['data'])
        self.assertTrue(resp.data['data']['gateway_order_id'].startswith('order_test_'))
        self.assertEqual(resp.data['data']['razorpay_key_id'], Configurations.razorpay_key_id)
        # ₹1500.00 -> 150000 paise, the unit Razorpay's Orders API and Checkout expect.
        self.assertEqual(resp.data['data']['amount'], 150000)
        self.assertEqual(resp.data['data']['currency'], 'INR')
        payment = Payment.objects.get(payment_id=resp.data['data']['payment_id'])
        self.assertEqual(str(payment.amount), '1500.00')
        self.assertEqual(str(payment.commission_amount), '150.00')
        self.assertEqual(payment.gateway, 'razorpay')
        self.assertEqual(payment.gateway_order_id, resp.data['data']['gateway_order_id'])
        # Real order.create() was actually called with the server-derived amount, in paise.
        self.mock_razorpay_client.order.create.assert_called_once()
        call_kwargs = self.mock_razorpay_client.order.create.call_args.kwargs
        self.assertEqual(call_kwargs['data']['amount'], 150000)
        self.assertEqual(call_kwargs['data']['currency'], 'INR')

    def test_initiate_payment_exceeding_remaining_due_returns_400(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000282', artist_phone='+919000000283')
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id, 'amount': '9999.00'}, format='json')
        self.assertEqual(resp.status_code, 400)
        # Rejected before any gateway call was ever made — amount is never trusted from the client.
        self.mock_razorpay_client.order.create.assert_not_called()

    def test_initiate_payment_gateway_failure_marks_payment_failed(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000291', artist_phone='+919000000292')
        self.mock_razorpay_client.order.create.side_effect = razorpay.errors.BadRequestError('gateway unavailable')
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'failed')
        self.assertIn('gateway unavailable', payment.failure_reason)

    def test_get_all_payments_returns_own_only(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000286', artist_phone='+919000000287')
        client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        other_client, _, _, other_booking = self._make_booking(customer_phone='+919000000288', artist_phone='+919000000289')
        other_client.post(self.initiate_url, {'booking_id': other_booking.booking_id}, format='json')

        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)


# ─── Verify Payment ──────────────────────────────────────────────────────────────

class VerifyPaymentTest(TestCase):
    initiate_url = '/customers/payments/initiate/'
    verify_url = '/customers/payments/verify/'
    get_all_url = '/customers/payments/get_all/'

    def setUp(self):
        # Same RazorpayGateway singleton is used by both initiate_payment.py and
        # verify_payment.py — patching it once here (via either import path) mocks it
        # for both, since `from ... import RazorpayGateway` binds the same class object.
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}",
            'amount': data['amount'],
            'currency': data['currency'],
            'status': 'created',
        }
        mock_client.utility.verify_payment_signature.return_value = None  # no exception = valid
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def _initiate(self, customer_phone, artist_phone, price=1500):
        client, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        return client, customer, booking, resp.data['data']['gateway_order_id'], resp.data['data']['amount']

    def _mock_captured_payment(self, order_id, amount_paise):
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_test_123', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        # verify_payment.py validates the tamper-proof ORDER amount, not the payment's
        # charged amount (which can legitimately include a gateway surcharge) — see the
        # live-discovered surcharge finding this covers below.
        self._mock_paid_order(order_id, amount_paise)

    def _mock_paid_order(self, order_id, amount_paise):
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }

    def test_verify_payment_success(self):
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000390', '+919000000391')
        self._mock_captured_payment(order_id, amount_paise)

        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_123', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'paid')
        self.assertEqual(payment.gateway_payment_id, 'pay_test_123')
        self.assertIsNotNone(payment.paid_at)
        self.assertTrue(
            Notification.objects.filter(booking_id=booking.booking_id, type='payment_status', user_id=customer.user_id).exists()
        )

    def test_verify_payment_invalid_signature_marks_failed(self):
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000392', '+919000000393')
        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad sig')

        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_456', 'razorpay_signature': 'sig_bad',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'failed')
        self.assertEqual(payment.failure_reason, 'Signature verification failed')
        # Never even reached the API-fetch confirmation step.
        self.mock_razorpay_client.payment.fetch.assert_not_called()

    def test_verify_payment_success_after_prior_failure_clears_failure_reason(self):
        # Regression (found live): a failed attempt followed by a successful retry on the
        # same order must not leave a stale failure_reason sitting next to paidAt in the
        # transaction history — that would misrepresent a successful payment as failed.
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000406', '+919000000407')
        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')
        fail_resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_bad',
        }, format='json')
        self.assertEqual(fail_resp.status_code, 400)

        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = None
        self.mock_razorpay_client.utility.verify_payment_signature.return_value = None
        self._mock_captured_payment(order_id, amount_paise)
        success_resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_123', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(success_resp.status_code, 200)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'paid')
        self.assertIsNone(payment.failure_reason)

    def test_verify_payment_amount_mismatch_marks_failed(self):
        # Tampering must be caught at the ORDER's own amount (set at creation, so the
        # client can't inflate it) — not the payment's charged amount, which can
        # legitimately differ due to a gateway surcharge (see the surcharge test below).
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000394', '+919000000395')
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_test_789', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self._mock_paid_order(order_id, amount_paise - 1)  # order itself reports a different amount

        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_789', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'failed')

    def test_verify_payment_not_captured_marks_failed(self):
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000396', '+919000000397')
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_test_999', 'order_id': order_id, 'status': 'authorized', 'amount': amount_paise,
        }

        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_999', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'failed')

    def test_verify_payment_is_idempotent_on_repeat(self):
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000398', '+919000000399')
        self._mock_captured_payment(order_id, amount_paise)

        body = {'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_123', 'razorpay_signature': 'sig_ok'}
        first = client.post(self.verify_url, body, format='json')
        self.assertEqual(first.status_code, 200)
        second = client.post(self.verify_url, body, format='json')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['message'], 'Payment already verified')
        # The second call never re-hit the gateway at all.
        self.mock_razorpay_client.utility.verify_payment_signature.assert_called_once()
        self.mock_razorpay_client.payment.fetch.assert_called_once()

    def test_verify_payment_with_gateway_surcharge_still_succeeds(self):
        # Regression (found live via a real Razorpay Checkout): this account is
        # configured to pass the gateway fee to the customer, so the captured payment's
        # amount can legitimately exceed the order amount (order 150000 -> payment
        # 150570). The order's own amount/amount_paid is what must be trusted for
        # tamper detection, not the payment's charged amount.
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000408', '+919000000409')
        surcharge_paise = amount_paise + 570
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_surcharge', 'order_id': order_id, 'status': 'captured', 'amount': surcharge_paise,
        }
        self._mock_paid_order(order_id, amount_paise)

        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_surcharge', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        payment = Payment.objects.get(gateway_order_id=order_id)
        self.assertEqual(payment.status.name, 'paid')

    def test_verify_payment_unknown_order_returns_400(self):
        seed_payment_statuses()
        client, _ = make_customer(phone_number='+919000000400')
        resp = client.post(self.verify_url, {
            'razorpay_order_id': 'order_does_not_exist', 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_x',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_payment_wrong_customer_returns_400(self):
        seed_payment_statuses()
        _, customer, booking, order_id, amount_paise = self._initiate('+919000000401', '+919000000402')
        outsider_client, _ = make_customer(phone_number='+919000000403')
        resp = outsider_client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test_x', 'razorpay_signature': 'sig_x',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_failed_payment_leaves_booking_unconfirmable(self):
        # Scenario: failed payment -> booking must not be confirmable, and the failed
        # attempt stays visible in the transaction history rather than vanishing.
        seed_payment_statuses()
        client, customer, booking, order_id, amount_paise = self._initiate('+919000000405', '+919000000404')
        artist_client = make_client(User.objects.get(phone_number='+919000000404'))
        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')
        resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_bad',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'pending')

        confirm_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 400)
        self.assertIn('payment', confirm_resp.data['message'].lower())

        # The failed attempt is still visible in the customer's payment history.
        history_resp = client.get(self.get_all_url)
        self.assertEqual(history_resp.status_code, 200)
        statuses = {p['statusId'] for p in history_resp.data['data']['data']}
        failed_status_id = PaymentStatus.objects.get(name='failed').status_id
        self.assertIn(failed_status_id, statuses)


# ─── Failure / retry / abandonment scenarios ────────────────────────────────────

class PaymentFailureScenarioTest(TestCase):
    """Targeted coverage for the specific edge cases called out in the original brief
    that aren't already exercised incidentally by PaymentTest/VerifyPaymentTest above."""

    initiate_url = '/customers/payments/initiate/'
    verify_url = '/customers/payments/verify/'

    def setUp(self):
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

    def _setup_booking(self, customer_phone, artist_phone, price=1500):
        client, customer = make_customer(phone_number=customer_phone)
        _, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return client, customer, make_client(artist_user), booking

    def test_abandoned_checkout_leaves_booking_unconfirmable(self):
        # Scenario: customer initiates payment, then abandons checkout (closes the app,
        # loses network, etc.) and never calls /verify/ at all. No webhook exists to catch
        # this either (deliberate design choice) — the Payment simply stays 'pending'
        # forever unless the customer comes back and completes/retries it.
        seed_payment_statuses()
        client, customer, artist_client, booking = self._setup_booking('+919000000410', '+919000000411')
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 201)

        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'pending')
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'pending')

        confirm_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 400)

    def test_retry_after_failed_payment_succeeds_without_duplicate_booking(self):
        # Scenario: first payment attempt fails; customer retries by initiating a fresh
        # attempt against the SAME booking. Must not create a second booking, and the
        # successful retry must still unlock artist confirmation.
        seed_payment_statuses()
        client, customer, artist_client, booking = self._setup_booking('+919000000412', '+919000000413')

        first = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(first.status_code, 201)
        first_order_id = first.data['data']['gateway_order_id']
        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')
        fail_resp = client.post(self.verify_url, {
            'razorpay_order_id': first_order_id, 'razorpay_payment_id': 'pay_fail', 'razorpay_signature': 'sig_bad',
        }, format='json')
        self.assertEqual(fail_resp.status_code, 400)

        # Retry: a brand new payment attempt against the same booking.
        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = None
        self.mock_razorpay_client.utility.verify_payment_signature.return_value = None
        second = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(second.status_code, 201)
        second_order_id = second.data['data']['gateway_order_id']
        second_amount = second.data['data']['amount']
        self.assertNotEqual(first_order_id, second_order_id)

        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_retry_ok', 'order_id': second_order_id, 'status': 'captured', 'amount': second_amount,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': second_order_id, 'amount': second_amount, 'amount_paid': second_amount,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        success_resp = client.post(self.verify_url, {
            'razorpay_order_id': second_order_id, 'razorpay_payment_id': 'pay_retry_ok', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(success_resp.status_code, 200)

        self.assertEqual(Booking.objects.filter(booking_id=booking.booking_id).count(), 1)
        self.assertEqual(Payment.objects.filter(booking_id=booking.booking_id).count(), 2)

        confirm_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)

    def test_reinitiate_after_fully_paid_returns_400(self):
        # Scenario: customer refreshes/retries the booking screen after already paying in
        # full — must not be allowed to pay (or be charged) again for the same booking.
        seed_payment_statuses()
        client, customer, artist_client, booking = self._setup_booking('+919000000414', '+919000000415')

        first = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        order_id = first.data['data']['gateway_order_id']
        amount_paise = first.data['data']['amount']
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_paid_once', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        verify_resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_paid_once', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(verify_resp.status_code, 200)

        again_resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(again_resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_called_once()  # never called for the second attempt

    def test_payment_stays_paid_even_if_post_verify_notification_fails(self):
        # Scenario: payment succeeds and is durably recorded before any secondary,
        # more-fragile step (here, the customer notification) runs — a failure in that
        # step must not lose or roll back the payment. A subsequent /verify/ call then
        # recovers cleanly via the existing idempotency check.
        seed_payment_statuses()
        client, customer, artist_client, booking = self._setup_booking('+919000000416', '+919000000417')
        init_resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        order_id = init_resp.data['data']['gateway_order_id']
        amount_paise = init_resp.data['data']['amount']
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_notify_fail', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }

        with patch('sunndari_apps.payments.views.verify_payment.NotificationService.notify', side_effect=RuntimeError('notify boom')):
            resp = client.post(self.verify_url, {
                'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_notify_fail', 'razorpay_signature': 'sig_ok',
            }, format='json')
            self.assertEqual(resp.status_code, 400)  # the response reports failure...

        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'paid')  # ...but the payment was already durably recorded.

        # Recovery: a normal retry (notification working this time) is a clean idempotent no-op.
        retry_resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_notify_fail', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(retry_resp.status_code, 200)
        self.assertEqual(retry_resp.data['message'], 'Payment already verified')

        confirm_resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)


# ─── PaymentOrder (multi-booking grouped checkout) ───────────────────────────────

class PaymentOrderModelTest(TestCase):
    """Phase 1 model-layer tests — no /initiate_group/ endpoint yet, this only proves
    the schema and static methods work as Payment's own equivalents already do."""

    def test_create_and_get(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000060001')
        pending_status = PaymentStatus.objects.get(name='pending')

        order_id = PaymentOrder().create(
            customer_id=customer.user_id, total_amount='3000.00', status_id=pending_status.status_id,
        )
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(order['customer_id'], customer.user_id)
        self.assertEqual(str(order['total_amount']), '3000.00')
        self.assertEqual(order['status_id'], pending_status.status_id)
        self.assertTrue(order['gateway_order_id'].startswith('PENDING-'))
        self.assertIsNone(order['paid_at'])

    def test_set_gateway_order_and_lookup_by_it(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000060002')
        pending_status = PaymentStatus.objects.get(name='pending')
        order_id = PaymentOrder().create(
            customer_id=customer.user_id, total_amount='3000.00', status_id=pending_status.status_id,
        )

        PaymentOrder.set_gateway_order(order_id=order_id, gateway='razorpay', gateway_order_id='order_group_abc')
        fetched = PaymentOrder.get_by_gateway_order_id(gateway_order_id='order_group_abc')
        self.assertEqual(fetched['order_id'], order_id)
        self.assertEqual(fetched['gateway'], 'razorpay')

    def test_mark_paid_and_mark_failed(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000060003')
        pending_status = PaymentStatus.objects.get(name='pending')
        paid_status = PaymentStatus.objects.get(name='paid')
        failed_status = PaymentStatus.objects.get(name='failed')

        order_id = PaymentOrder().create(
            customer_id=customer.user_id, total_amount='3000.00', status_id=pending_status.status_id,
        )
        PaymentOrder.mark_paid(order_id=order_id, gateway_payment_id='pay_xyz', status_id=paid_status.status_id)
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(order['status_id'], paid_status.status_id)
        self.assertEqual(order['gateway_payment_id'], 'pay_xyz')
        self.assertIsNotNone(order['paid_at'])

        PaymentOrder.mark_failed(order_id=order_id, status_id=failed_status.status_id, failure_reason='boom')
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(order['status_id'], failed_status.status_id)
        self.assertEqual(order['failure_reason'], 'boom')

    def test_payment_can_link_to_an_order(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000060004')
        _, _, profile = make_artist(phone_number='+919000060005')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        pending_status = PaymentStatus.objects.get(name='pending')
        order_id = PaymentOrder().create(
            customer_id=customer.user_id, total_amount='1000.00', status_id=pending_status.status_id,
        )
        payment_id = Payment().create(
            booking_id=booking.booking_id, customer_id=customer.user_id, artist_id=profile.artist_id,
            amount=1000, commission_amount=100, artist_payout_amount=900,
            status_id=pending_status.status_id, order_id=order_id,
        )
        payment = Payment.get(payment_id=payment_id)
        self.assertEqual(payment['order_id'], order_id)

    def test_solo_payment_still_has_no_order_by_default(self):
        # Confirms Phase 1 is purely additive — a payment created the existing way
        # (no order_id passed) is completely unaffected.
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000060006')
        _, _, profile = make_artist(phone_number='+919000060007')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        pending_status = PaymentStatus.objects.get(name='pending')
        payment_id = Payment().create(
            booking_id=booking.booking_id, customer_id=customer.user_id, artist_id=profile.artist_id,
            amount=1000, commission_amount=100, artist_payout_amount=900, status_id=pending_status.status_id,
        )
        payment = Payment.get(payment_id=payment_id)
        self.assertIsNone(payment['order_id'])


# ─── POST /customers/payments/initiate_group/ ────────────────────────────────────

class InitiateGroupPaymentTest(TestCase):
    initiate_group_url = '/customers/payments/initiate_group/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_group_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def _make_booking(self, customer, artist_phone, price, commission_rate=None):
        _, _, profile = make_artist(phone_number=artist_phone)
        if commission_rate is not None:
            profile.commission_rate = commission_rate
            profile.save()
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return profile, booking

    def test_group_of_three_creates_one_order_and_three_payments(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061001')
        _, b1 = self._make_booking(customer, '+919000061002', price=1000, commission_rate='10.00')
        _, b2 = self._make_booking(customer, '+919000061003', price=1500, commission_rate='10.00')
        _, b3 = self._make_booking(customer, '+919000061004', price=2000, commission_rate='10.00')

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id, b3.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        # ₹1000 + ₹1500 + ₹2000 = ₹4500 -> 450000 paise.
        self.assertEqual(resp.data['data']['amount'], 450000)
        self.assertEqual(len(resp.data['data']['payment_ids']), 3)

        order_id = resp.data['data']['order_id']
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(str(order['total_amount']), '4500.00')
        self.assertEqual(order['gateway'], 'razorpay')

        payments = Payment.objects.filter(order_id=order_id).order_by('amount')
        self.assertEqual(payments.count(), 3)
        self.assertEqual([str(p.amount) for p in payments], ['1000.00', '1500.00', '2000.00'])
        for p in payments:
            self.assertEqual(str(p.commission_amount), str(round(p.amount * 10 / 100, 2)))
            self.assertEqual(p.status.name, 'pending')

    def test_duplicate_booking_id_rejected(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061005')
        _, b1 = self._make_booking(customer, '+919000061006', price=1000)

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b1.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        self.assertFalse(Payment.objects.filter(booking_id=b1.booking_id).exists())

    def test_single_booking_id_rejected_by_serializer(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061007')
        _, b1 = self._make_booking(customer, '+919000061008', price=1000)

        resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id]}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_booking_not_owned_by_customer_blocks_whole_group_and_creates_nothing(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061009')
        _, b1 = self._make_booking(customer, '+919000061010', price=1000)
        other_client, other_customer = make_customer(phone_number='+919000061011')
        _, b2 = self._make_booking(other_customer, '+919000061012', price=1000)

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        # Neither booking got a Payment row -- validated before anything was created.
        self.assertFalse(Payment.objects.filter(booking_id__in=[b1.booking_id, b2.booking_id]).exists())
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_already_fully_paid_booking_blocks_whole_group(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061013')
        _, b1 = self._make_booking(customer, '+919000061014', price=1000)
        _, b2 = self._make_booking(customer, '+919000061015', price=1000)
        paid_status = PaymentStatus.objects.get(name='paid')
        Payment().create(
            booking_id=b2.booking_id, customer_id=customer.user_id, artist_id=b2.artist_id,
            amount=1000, commission_amount=100, artist_payout_amount=900, status_id=paid_status.status_id,
        )

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        self.assertFalse(Payment.objects.filter(booking_id=b1.booking_id).exists())

    def test_gateway_failure_marks_order_and_all_payments_failed(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000061016')
        _, b1 = self._make_booking(customer, '+919000061017', price=1000)
        _, b2 = self._make_booking(customer, '+919000061018', price=1000)
        self.mock_razorpay_client.order.create.side_effect = razorpay.errors.BadRequestError('gateway down')

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

        order = PaymentOrder.objects.get(customer_id=customer.user_id)
        self.assertEqual(order.status.name, 'failed')
        payments = Payment.objects.filter(order=order)
        self.assertEqual(payments.count(), 2)
        for p in payments:
            self.assertEqual(p.status.name, 'failed')

    def test_redemption_applies_only_to_first_booking(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000062001')
        profile1, b1 = self._make_booking(customer, '+919000062002', price=1000, commission_rate='10.00')
        _, b2 = self._make_booking(customer, '+919000062003', price=1500, commission_rate='10.00')
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # 50000 coins at ₹0.01/coin
        CustomerWallet.credit(customer_id=customer.user_id, coins=50000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id], 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['coins_redeemed'], 50000)
        self.assertEqual(str(resp.data['data']['redemption_discount']), '500.00')
        # (₹1000 - ₹500) + ₹1500 = ₹2000 -> 200000 paise.
        self.assertEqual(resp.data['data']['amount'], 200000)

        order_id = resp.data['data']['order_id']
        p1 = Payment.objects.get(order_id=order_id, booking_id=b1.booking_id)
        p2 = Payment.objects.get(order_id=order_id, booking_id=b2.booking_id)
        self.assertEqual(str(p1.amount), '500.00')  # discounted
        self.assertEqual(str(p2.amount), '1500.00')  # untouched
        # Commission on booking 1 stays computed off the PRE-redemption ₹1000 — the
        # platform, not the artist, absorbs the discount.
        self.assertEqual(str(p1.commission_amount), '100.00')
        self.assertEqual(str(p1.artist_payout_amount), '900.00')

        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)
        redemption_txn = CoinTransaction.objects.get(wallet=wallet, transaction_type='REDEMPTION')
        self.assertEqual(redemption_txn.booking_id, b1.booking_id)
        self.assertEqual(redemption_txn.payment_id, p1.payment_id)

    def test_tier_exceeding_first_booking_amount_is_blocked_even_if_group_total_covers_it(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000062004')
        _, b1 = self._make_booking(customer, '+919000062005', price=1000)
        _, b2 = self._make_booking(customer, '+919000062006', price=1000)
        # ₹2000 tier exceeds b1's own ₹1000 price, even though the ₹2000 group total
        # would cover it -- must be blocked per the "first booking only" allocation rule.
        tier = RedemptionTier.objects.create(rupee_value='2000.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=200000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id], 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 200000)  # untouched

    def test_insufficient_coins_fails_whole_group(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000062007')
        _, b1 = self._make_booking(customer, '+919000062008', price=1000)
        _, b2 = self._make_booking(customer, '+919000062009', price=1000)
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=100, transaction_type='ADJUSTMENT')  # not enough

        resp = client.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id], 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

        order = PaymentOrder.objects.get(customer_id=customer.user_id)
        self.assertEqual(order.status.name, 'failed')
        payments = Payment.objects.filter(order=order)
        self.assertEqual(payments.count(), 2)
        for p in payments:
            self.assertEqual(p.status.name, 'failed')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 100)  # untouched

    def test_no_redemption_tier_behaves_exactly_as_phase_2(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000062010')
        _, b1 = self._make_booking(customer, '+919000062011', price=1000)
        _, b2 = self._make_booking(customer, '+919000062012', price=1000)

        resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id, b2.booking_id]}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn('coins_redeemed', resp.data['data'])
        self.assertEqual(resp.data['data']['amount'], 200000)


# ─── /verify/ extended for a grouped PaymentOrder ────────────────────────────────

class VerifyGroupPaymentTest(TestCase):
    initiate_group_url = '/customers/payments/initiate_group/'
    verify_url = '/customers/payments/verify/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_group_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_client.utility.verify_payment_signature.return_value = None
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def _make_booking(self, customer, artist_phone, price):
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return profile, booking

    def test_verify_marks_order_and_all_payments_paid(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063001')
        _, b1 = self._make_booking(customer, '+919000063002', price=1000)
        _, b2 = self._make_booking(customer, '+919000063003', price=1500)

        init_resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id, b2.booking_id]}, format='json')
        self.assertEqual(init_resp.status_code, 201)
        order_id = init_resp.data['data']['order_id']
        gateway_order_id = init_resp.data['data']['gateway_order_id']
        amount_paise = init_resp.data['data']['amount']

        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_group_ok', 'order_id': gateway_order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': gateway_order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            verify_resp = client.post(self.verify_url, {
                'razorpay_order_id': gateway_order_id, 'razorpay_payment_id': 'pay_group_ok', 'razorpay_signature': 'sig_ok',
            }, format='json')
        self.assertEqual(verify_resp.status_code, 200)
        self.assertEqual(verify_resp.data['message'], 'Payment verified successfully')

        order = PaymentOrder.objects.get(order_id=order_id)
        self.assertEqual(order.status.name, 'paid')
        self.assertEqual(order.gateway_payment_id, 'pay_group_ok')
        payments = Payment.objects.filter(order=order)
        self.assertEqual(payments.count(), 2)
        for p in payments:
            self.assertEqual(p.status.name, 'paid')
            self.assertEqual(p.gateway_payment_id, 'pay_group_ok')
        self.assertTrue(
            Notification.objects.filter(booking_id=b1.booking_id, type='payment_status', user_id=customer.user_id).exists()
        )
        self.assertTrue(
            Notification.objects.filter(booking_id=b2.booking_id, type='payment_status', user_id=customer.user_id).exists()
        )

    def test_verify_is_idempotent_on_repeat(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063004')
        _, b1 = self._make_booking(customer, '+919000063005', price=1000)
        _, b2 = self._make_booking(customer, '+919000063006', price=1000)
        init_resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id, b2.booking_id]}, format='json')
        gateway_order_id = init_resp.data['data']['gateway_order_id']
        amount_paise = init_resp.data['data']['amount']

        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_x', 'order_id': gateway_order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': gateway_order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        body = {'razorpay_order_id': gateway_order_id, 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_ok'}
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            first = client.post(self.verify_url, body, format='json')
            second = client.post(self.verify_url, body, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['message'], 'Payment already verified')
        self.mock_razorpay_client.utility.verify_payment_signature.assert_called_once()

    def test_invalid_signature_fails_whole_group(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063007')
        _, b1 = self._make_booking(customer, '+919000063008', price=1000)
        _, b2 = self._make_booking(customer, '+919000063009', price=1000)
        init_resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id, b2.booking_id]}, format='json')
        gateway_order_id = init_resp.data['data']['gateway_order_id']
        order_id = init_resp.data['data']['order_id']

        self.mock_razorpay_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            resp = client.post(self.verify_url, {
                'razorpay_order_id': gateway_order_id, 'razorpay_payment_id': 'pay_bad', 'razorpay_signature': 'sig_bad',
            }, format='json')
        self.assertEqual(resp.status_code, 400)

        order = PaymentOrder.objects.get(order_id=order_id)
        self.assertEqual(order.status.name, 'failed')
        payments = Payment.objects.filter(order=order)
        for p in payments:
            self.assertEqual(p.status.name, 'failed')
            self.assertEqual(p.failure_reason, 'Signature verification failed')

    def test_unknown_group_order_id_returns_400(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063010')
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            resp = client.post(self.verify_url, {
                'razorpay_order_id': 'order_does_not_exist', 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_x',
            }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_wrong_customer_cannot_verify_someone_elses_group(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063011')
        _, b1 = self._make_booking(customer, '+919000063012', price=1000)
        _, b2 = self._make_booking(customer, '+919000063013', price=1000)
        init_resp = client.post(self.initiate_group_url, {'booking_ids': [b1.booking_id, b2.booking_id]}, format='json')
        gateway_order_id = init_resp.data['data']['gateway_order_id']

        outsider_client, _ = make_customer(phone_number='+919000063014')
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            resp = outsider_client.post(self.verify_url, {
                'razorpay_order_id': gateway_order_id, 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 'sig_x',
            }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_solo_payment_verify_still_works_unaffected(self):
        # Confirms the fallback never interferes with the existing solo path -- a solo
        # /initiate/ payment's gateway_order_id is found and handled by the first branch,
        # never falling through to the PaymentOrder lookup.
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000063015')
        _, _, profile = make_artist(phone_number='+919000063016')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        with patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            init_resp = client.post('/customers/payments/initiate/', {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(init_resp.status_code, 201)
        order_id_str = init_resp.data['data']['gateway_order_id']
        amount_paise = init_resp.data['data']['amount']

        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_solo', 'order_id': order_id_str, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id_str, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client', return_value=self.mock_razorpay_client):
            verify_resp = client.post(self.verify_url, {
                'razorpay_order_id': order_id_str, 'razorpay_payment_id': 'pay_solo', 'razorpay_signature': 'sig_ok',
            }, format='json')
        self.assertEqual(verify_resp.status_code, 200)
        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'paid')
        self.assertIsNone(payment.order)
