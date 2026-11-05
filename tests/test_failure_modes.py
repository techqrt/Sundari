"""What happens when something outside our control goes wrong, or arrives at the wrong time.

Every test asserts the SAFE outcome: money is never kept for a service that will not happen, never
claimed as returned when it was not, and coins never end up spent twice or created from nothing.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.customers.models import Booking
from tests.booking_address import address_for
from sunndari_apps.customers.tasks import cancel_stale_pending_bookings
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models import CoinConfig, CoinTransaction, CustomerWallet, RedemptionTier

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type, make_package,
    make_location_preference, make_schedule, seed_booking_statuses, seed_payment_statuses, next_weekday,
)

INITIATE = '/customers/payments/initiate/'
VERIFY = '/customers/payments/verify/'


class GatewayFixture:
    """A booking (pending, ₹2000) plus a mocked Razorpay gateway; shared by the failure-mode and the
    payment-reliability tests."""

    def setUp(self):
        super().setUp()
        seed_booking_statuses()
        seed_payment_statuses()
        CoinConfig.objects.create()
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        self.gateway.utility.verify_payment_signature.return_value = None
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.artist_client, _, self.profile = make_artist(phone_number='+919200000001')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=2000, duration=60)
        location = make_location_type()
        make_location_preference(self.profile, location)
        day = next_weekday(2)
        make_schedule(self.profile, day_of_week=day.weekday())
        self.client, self.customer = make_customer(phone_number='+919200000002')
        resp = self.client.post('/customers/bookings/create/', {**address_for(self.client), 
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': location.location_type_id, 'booking_date': day.strftime('%d-%m-%y'), 'start_time': '10:00:00',
        }, format='json')
        self.booking_id = resp.data['data']['booking_id']

    # ── helpers ──────────────────────────────────────────────────────────────

    def _initiate(self, **extra):
        return self.client.post(INITIATE, {'booking_id': self.booking_id, **extra}, format='json')

    def _gateway_says_paid(self, order_id, paise, payment_id='pay_ok', **overrides):
        self.gateway.payment.fetch.return_value = {'id': payment_id, 'order_id': order_id, 'status': 'captured', 'amount': paise}
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': paise, 'amount_due': 0,
                                                 'currency': 'INR', 'status': 'paid', **overrides}

    def _verify(self, order_id, payment_id='pay_ok', client=None):
        return (client or self.client).post(VERIFY, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig',
        }, format='json')

    def _pay(self):
        resp = self._initiate()
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        self._gateway_says_paid(order_id, paise)
        self.assertEqual(self._verify(order_id).status_code, 200)
        return order_id

    def _booking(self):
        return Booking.objects.get(booking_id=self.booking_id)


class GatewayFailureTest(GatewayFixture, TestCase):

    # ── refunds ──────────────────────────────────────────────────────────────

    def test_a_failed_refund_is_never_reported_as_returned_and_can_be_retried(self):
        self._pay()
        self.gateway.payment.refund.side_effect = Exception('gateway timeout')
        resp = self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        payment = Payment.objects.get(booking_id=self.booking_id)
        self.assertEqual(payment.status.name, 'paid')                     # money has NOT gone back, so we must not say it has
        self.assertIn('Refund failed', payment.failure_reason)
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='refund_pending').exists())

        self.gateway.payment.refund.side_effect = None                    # gateway recovers
        out = StringIO()
        call_command('retry_refunds', stdout=out)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, 'refunded')
        self.assertIn('refunded=1', out.getvalue())
        self.gateway.payment.refund.assert_called_with('pay_ok', {
            'amount': 200000, 'notes': {'payment_id': str(payment.payment_id), 'booking_id': str(self.booking_id)},
        })

    def test_retrying_refunds_never_refunds_the_same_payment_twice(self):
        self._pay()
        self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        calls_after_cancel = self.gateway.payment.refund.call_count
        for _ in range(3):
            call_command('retry_refunds', stdout=StringIO())
        self.assertEqual(self.gateway.payment.refund.call_count, calls_after_cancel)

    # ── tampered or mismatched confirmations ─────────────────────────────────

    def test_an_underpaid_order_does_not_settle_the_booking(self):
        resp = self._initiate()
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        self._gateway_says_paid(order_id, paise, amount_paid=paise - 100, status='attempted')
        self.assertEqual(self._verify(order_id).status_code, 400)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'failed')
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_a_payment_that_belongs_to_a_different_order_is_refused(self):
        order_id = self._initiate().data['data']['gateway_order_id']
        self._gateway_says_paid('order_somebody_else', 200000)
        self.assertEqual(self._verify(order_id).status_code, 400)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_a_payment_captured_for_a_smaller_amount_than_the_order_is_refused(self):
        resp = self._initiate()
        order_id = resp.data['data']['gateway_order_id']
        self._gateway_says_paid(order_id, 50000)                           # order says ₹500, we quoted ₹2000
        self.assertEqual(self._verify(order_id).status_code, 400)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_someone_else_cannot_confirm_my_payment(self):
        order_id = self._initiate().data['data']['gateway_order_id']
        self._gateway_says_paid(order_id, 200000)
        other_client, _ = make_customer(phone_number='+919200000003')
        self.assertEqual(self._verify(order_id, client=other_client).status_code, 400)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    # ── the gateway is down ──────────────────────────────────────────────────

    def test_gateway_outage_at_checkout_costs_the_customer_nothing(self):
        import razorpay
        RedemptionTier.objects.create(rupee_value=Decimal('100.00'))        # 10,000 coins at ₹0.01
        CustomerWallet.credit(customer_id=self.customer.user_id, coins=10000, transaction_type='ADJUSTMENT')
        self.gateway.order.create.side_effect = razorpay.errors.ServerError('down')
        tier = RedemptionTier.objects.get()
        resp = self._initiate(redemption_tier_id=tier.tier_id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CustomerWallet.objects.get(customer_id=self.customer.user_id).balance_coins, 10000)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='REDEMPTION').count(), 0)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'failed')

    def test_after_an_outage_the_customer_can_simply_try_again(self):
        import razorpay
        self.gateway.order.create.side_effect = razorpay.errors.ServerError('down')
        self.assertEqual(self._initiate().status_code, 400)
        self.gateway.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created'}
        self.assertEqual(self._initiate().status_code, 201)

    # ── time: the slot lock expires while the customer is paying ─────────────

    def test_paying_after_the_slot_lock_expired_never_keeps_money_for_a_cancelled_booking(self):
        resp = self._initiate()
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        self.assertEqual(self._booking().status.name, 'cancelled')

        # The customer was still on the payment page: they pay at the gateway and the app confirms it.
        self._gateway_says_paid(order_id, paise)
        verify = self._verify(order_id)
        payment = Payment.objects.get(booking_id=self.booking_id)
        self.assertEqual(verify.status_code, 400)                          # the customer is told it was not applied ...
        self.assertEqual(payment.status.name, 'refunded')                   # ... and the money is on its way back
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)
        self.gateway.payment.refund.assert_called_once_with('pay_ok', {
            'amount': paise, 'notes': {'payment_id': str(payment.payment_id), 'booking_id': str(self.booking_id)},
        })
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='refund_initiated').exists())
        self.assertEqual(self._booking().status.name, 'cancelled')          # the cancelled booking is not resurrected

    def test_replaying_the_late_confirmation_never_refunds_twice(self):
        resp = self._initiate()
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        self._gateway_says_paid(order_id, paise)
        for _ in range(3):
            self._verify(order_id)
        self.assertEqual(self.gateway.payment.refund.call_count, 1)

    def test_a_lost_refund_reply_is_reconciled_instead_of_refunding_twice(self):
        # The gateway accepted the refund but the response never reached us (timeout). Reporting that as a
        # failure would make the retry job refund the customer a second time.
        self._pay()
        self.gateway.payment.refund.side_effect = Exception('read timeout')
        self.gateway.payment.fetch.return_value = {'id': 'pay_ok', 'status': 'refunded', 'amount_refunded': 200000}
        self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        payment = Payment.objects.get(booking_id=self.booking_id)
        self.assertEqual(payment.status.name, 'refunded')
        self.assertEqual(payment.refund_attempts, 0)

    def test_abandoned_checkout_with_coins_gives_the_coins_back_when_the_lock_expires(self):
        RedemptionTier.objects.create(rupee_value=Decimal('100.00'))
        CustomerWallet.credit(customer_id=self.customer.user_id, coins=10000, transaction_type='ADJUSTMENT')
        tier = RedemptionTier.objects.get()
        self.assertEqual(self._initiate(redemption_tier_id=tier.tier_id).status_code, 201)
        self.assertEqual(CustomerWallet.objects.get(customer_id=self.customer.user_id).balance_coins, 0)
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        cancel_stale_pending_bookings()                                    # the sweep runs every minute: must be idempotent
        self.assertEqual(CustomerWallet.objects.get(customer_id=self.customer.user_id).balance_coins, 10000)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='REVERSAL').count(), 1)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='CASHBACK').count(), 0)

    def test_a_paid_booking_is_never_swept_away_by_the_expiry_job(self):
        self._pay()
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(hours=1))
        cancel_stale_pending_bookings()
        self.assertEqual(self._booking().status.name, 'pending')
