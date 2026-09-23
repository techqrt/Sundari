import razorpay
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase

from sunndari_apps.core.models import BookingStatus, PaymentStatus
from sunndari_apps.customers.models import Booking
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.wallet.models import RedemptionTier, CustomerWallet, CoinTransaction
from sunndari_apps.wallet.models.coin_config import CoinConfig

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type, make_package,
    make_booking, seed_payment_statuses, seed_booking_statuses, next_weekday,
)


class GroupPaymentFullLifecycleSmokeTest(TestCase):
    """End-to-end smoke test for the group-payment feature, driven through the real
    HTTP endpoints, covering interactions with the wallet/cashback system that the
    per-unit tests in test_payments.py don't exercise together: cancelling one
    booking inside an already-paid group (must not disturb its siblings or the
    order), cancelling the specific booking that carried the redemption discount
    (must reverse only that redemption), and cashback still computing correctly on
    a booking that was settled via a group checkout rather than a solo payment."""

    initiate_group_url = '/customers/payments/initiate_group/'
    verify_url = '/customers/payments/verify/'
    cancel_url = '/customers/bookings/cancel/'

    def setUp(self):
        seed_payment_statuses()
        seed_booking_statuses()
        CoinConfig.objects.get_or_create(pk=1, defaults={
            'cashback_percentage': Decimal('10.00'),
            'coin_value_rupees': Decimal('0.01'),
            'coin_expiry_days': 365,
        })
        patcher = patch('sunndari_apps.payments.views.initiate_group_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_client = MagicMock()
        self.mock_client.order.create.side_effect = lambda data: {
            'id': f"order_smoke_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_get_client.return_value = self.mock_client

        self.client_api, self.customer = make_customer(phone_number='+919000099001')

    def _make_booking(self, price, phone):
        _, _, profile = make_artist(phone_number=phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            self.customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return profile, booking

    def _verify(self, gateway_order_id, total_amount):
        expected_paise = int(round(total_amount * 100))
        with patch('sunndari_apps.payments.views.verify_payment.RazorpayGateway') as MockGw:
            mock_client = MockGw.get_client.return_value
            mock_client.utility.verify_payment_signature.return_value = None
            mock_client.payment.fetch.return_value = {'order_id': gateway_order_id, 'status': 'captured'}
            mock_client.order.fetch.return_value = {'amount': expected_paise, 'amount_paid': expected_paise, 'status': 'paid'}
            return self.client_api.post(self.verify_url, {
                'razorpay_order_id': gateway_order_id,
                'razorpay_payment_id': f'pay_{gateway_order_id}',
                'razorpay_signature': 'sig_fake',
            }, format='json')

    def test_full_lifecycle(self):
        # --- seed coins the customer can redeem ---
        tier = RedemptionTier.objects.create(rupee_value=Decimal('50.00'), is_active=True)
        CustomerWallet.award_cashback(customer_id=self.customer.user_id, booking_id=1, service_amount=Decimal('50000.00'))
        wallet = CustomerWallet.objects.get(customer_id=self.customer.user_id)
        seed_balance = wallet.balance_coins
        self.assertGreaterEqual(seed_balance, tier.coin_cost)

        _, b1 = self._make_booking(500, '+919000099002')
        _, b2 = self._make_booking(300, '+919000099003')

        # --- SCENARIO A: initiate group with redemption on b1 (first in list) ---
        resp = self.client_api.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
            'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        data = resp.data['data']
        self.assertEqual(data['coins_redeemed'], tier.coin_cost)
        self.assertEqual(str(data['redemption_discount']), '50.00')

        order_id = data['order_id']
        gateway_order_id = data['gateway_order_id']
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(order['total_amount'], Decimal('750.00'))  # (500-50) + 300

        payments = list(Payment.objects.filter(order_id=order_id).order_by('booking_id'))
        p1 = next(p for p in payments if p.booking_id == b1.booking_id)
        p2 = next(p for p in payments if p.booking_id == b2.booking_id)
        self.assertEqual(p1.amount, Decimal('450.00'))
        self.assertEqual(p2.amount, Decimal('300.00'))
        self.assertEqual(p1.commission_amount, round(Decimal('500.00') * p1.artist.commission_rate / 100, 2))

        redemption_txn = CoinTransaction.objects.get(transaction_type='REDEMPTION', booking_id=b1.booking_id)
        self.assertEqual(redemption_txn.payment_id, p1.payment_id)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, seed_balance - tier.coin_cost)

        # --- SCENARIO B: verify group payment ---
        vresp = self._verify(gateway_order_id, order['total_amount'])
        self.assertEqual(vresp.status_code, 200, vresp.data)

        order = PaymentOrder.get(order_id=order_id)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(order['status_id'], PaymentStatus.objects.get(name='paid').status_id)
        self.assertEqual(p1.status.name, 'paid')
        self.assertEqual(p2.status.name, 'paid')

        # Idempotent re-verify must be a safe no-op, same guarantee as solo payments.
        vresp2 = self._verify(gateway_order_id, order['total_amount'])
        self.assertEqual(vresp2.status_code, 200)
        self.assertEqual(vresp2.data['message'], 'Payment already verified')

        # --- SCENARIO C: total_settled_for_booking counts cash + redeemed value correctly ---
        self.assertEqual(Payment.total_settled_for_booking(booking_id=b1.booking_id), Decimal('500.00'))
        self.assertEqual(Payment.total_settled_for_booking(booking_id=b2.booking_id), Decimal('300.00'))

        # --- SCENARIO D: cancel b2 (non-redeemed) must not disturb b1 or the order ---
        resp = self.client_api.put(self.cancel_url, {'booking_id': b2.booking_id, 'reason': 'changed my mind'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p2.status.name, 'refunded')
        self.assertEqual(p1.status.name, 'paid')
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, seed_balance - tier.coin_cost)  # unchanged: no redemption on b2

        # --- SCENARIO E: cancel b1 (the redeemed booking) must refund it AND reverse its coins ---
        balance_before = wallet.balance_coins
        resp = self.client_api.put(self.cancel_url, {'booking_id': b1.booking_id, 'reason': 'artist unavailable'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        p1.refresh_from_db()
        self.assertEqual(p1.status.name, 'refunded')
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, balance_before + tier.coin_cost)
        self.assertTrue(CoinTransaction.objects.filter(
            transaction_type='REVERSAL', reference_transaction_id=redemption_txn.transaction_id,
        ).exists())

        # Order-level status is untouched by per-booking cancellation (by design).
        order = PaymentOrder.get(order_id=order_id)
        self.assertEqual(order['status_id'], PaymentStatus.objects.get(name='paid').status_id)

    def test_cashback_awarded_correctly_for_group_paid_booking(self):
        _, b1 = self._make_booking(200, '+919000099010')
        _, b2 = self._make_booking(100, '+919000099011')

        resp = self.client_api.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        data = resp.data['data']
        order = PaymentOrder.get(order_id=data['order_id'])
        vresp = self._verify(data['gateway_order_id'], order['total_amount'])
        self.assertEqual(vresp.status_code, 200, vresp.data)

        wallet, _ = CustomerWallet.objects.get_or_create(customer_id=self.customer.user_id)
        before = wallet.balance_coins
        cashback_txn = CustomerWallet.award_cashback(
            customer_id=self.customer.user_id, booking_id=b1.booking_id, service_amount=b1.total_amount,
        )
        wallet.refresh_from_db()
        expected_coins = int((Decimal('200.00') * Decimal('10.00') / 100) / Decimal('0.01'))
        self.assertIsNotNone(cashback_txn)
        self.assertEqual(wallet.balance_coins, before + expected_coins)

    def test_duplicate_booking_and_orphan_free_rejection(self):
        _, b1 = self._make_booking(10, '+919000099020')
        _, b2 = self._make_booking(500, '+919000099021')
        tier = RedemptionTier.objects.create(rupee_value=Decimal('50.00'), is_active=True)

        resp = self.client_api.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b1.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

        # Redemption exceeding the first booking's own amount (b1=10, tier=50) must be
        # rejected and leave no orphaned rows.
        resp = self.client_api.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
            'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking_id__in=[b1.booking_id, b2.booking_id]).exists())
        self.assertEqual(PaymentOrder.objects.count(), 0)

    def test_gateway_failure_cascades_to_order_and_all_payments(self):
        _, b1 = self._make_booking(100, '+919000099030')
        _, b2 = self._make_booking(150, '+919000099031')
        self.mock_client.order.create.side_effect = razorpay.errors.ServerError('gateway down')

        resp = self.client_api.post(self.initiate_group_url, {
            'booking_ids': [b1.booking_id, b2.booking_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

        order = PaymentOrder.objects.filter(payments__booking_id=b1.booking_id).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status.name, 'failed')
        for p in Payment.objects.filter(booking_id__in=[b1.booking_id, b2.booking_id]):
            self.assertEqual(p.status.name, 'failed')
