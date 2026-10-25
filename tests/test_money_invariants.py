"""Randomized end-to-end money simulation.

Many customers book, pay (cash, cash + coins, or entirely with coins), and then complete, cancel or
abandon the booking — all through the real HTTP APIs. After every run of the dice the accounting rules
that must ALWAYS hold are checked, so a bug in any single flow shows up as a broken invariant rather
than needing someone to guess the right scenario.

The random generator is seeded, so a failure reproduces exactly.
"""
import collections
import random
from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
from unittest.mock import patch, MagicMock

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.customers.models import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models import CoinConfig, CoinTransaction, CustomerWallet, RedemptionTier

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type, make_package,
    make_location_preference, make_schedule, seed_booking_statuses, seed_payment_statuses, next_weekday,
)

SEED = 20261023
RUNS = 60
BATCH_TYPES = CoinTransaction.BATCH_TRANSACTION_TYPES


class MoneyInvariantSimulation(TestCase):

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        self.config = CoinConfig.objects.create()                       # shipped defaults: 10 paise per ₹100, ₹0.01 / coin
        self.rng = random.Random(SEED)
        self.location = make_location_type()
        self.sub = make_sub_category()
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        self.gateway.utility.verify_payment_signature.return_value = None
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.problems = []
        self.tally = collections.Counter()

    # ── building blocks ──────────────────────────────────────────────────────

    def _new_booking(self, n):
        artist_client, _, profile = make_artist(phone_number=f'+9195{n:08d}')
        price = self.rng.choice([500, 750, 1000, 1500, 2000, 2500, 3000, 5000])
        package = make_package(profile, sub_category=self.sub, price=price, duration=60)
        make_location_preference(profile, self.location)
        day = next_weekday(self.rng.randrange(7))
        make_schedule(profile, day_of_week=day.weekday())
        client, customer = make_customer(phone_number=f'+9196{n:08d}')
        resp = client.post('/customers/bookings/create/', {
            'artist_id': profile.artist_id, 'package_id': package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': day.strftime('%d-%m-%y'), 'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        return client, artist_client, customer, Booking.objects.get(booking_id=resp.data['data']['booking_id'])

    def _tier_for(self, rupees):
        tier, _ = RedemptionTier.objects.get_or_create(rupee_value=Decimal(rupees))
        return tier

    def _pay(self, client, booking, mode):
        """mode: 'cash' | 'partial' (coins cover part) | 'full' (coins cover everything)."""
        payload = {'booking_id': booking.booking_id}
        tier = None
        if mode in ('partial', 'full'):
            tier = self._tier_for(booking.total_amount if mode == 'full' else self.rng.choice([10, 50, 100]))
            CustomerWallet.credit(customer_id=booking.customer_id, coins=tier.coin_cost + self.rng.choice([0, 7, 500]),
                                  transaction_type='ADJUSTMENT')
            payload['redemption_tier_id'] = tier.tier_id
        resp = client.post('/customers/payments/initiate/', payload, format='json')
        if resp.status_code != 201:
            self.problems.append(f'booking {booking.booking_id}: initiate({mode}) -> {resp.status_code} {resp.data}')
            return
        if resp.data['data'].get('fully_covered_by_coins'):
            return
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        self.gateway.payment.fetch.return_value = {'id': f'pay_{order_id}', 'order_id': order_id, 'status': 'captured', 'amount': paise}
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': paise, 'amount_due': 0,
                                                 'currency': 'INR', 'status': 'paid'}
        verify = client.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': f'pay_{order_id}', 'razorpay_signature': 'sig',
        }, format='json')
        if verify.status_code != 200:
            self.problems.append(f'booking {booking.booking_id}: verify -> {verify.status_code} {verify.data}')

    def _complete(self, artist_client, booking):
        resp = artist_client.put('/artists/bookings/update_status/', {'booking_id': booking.booking_id, 'status': 'confirmed'}, format='json')
        if resp.status_code != 200:
            self.problems.append(f'booking {booking.booking_id}: confirm -> {resp.status_code} {resp.data}')
            return
        Booking.objects.filter(booking_id=booking.booking_id).update(
            status=type(booking.status).objects.get(name='in_progress'),
            completion_pin=4242, completion_pin_expiry=timezone.now() + timedelta(hours=2),
        )
        done = artist_client.put('/artists/bookings/completion_pin/verify/', {'booking_id': booking.booking_id, 'completion_pin': 4242}, format='json')
        if done.status_code != 200:
            self.problems.append(f'booking {booking.booking_id}: complete -> {done.status_code} {done.data}')

    # ── the dice ─────────────────────────────────────────────────────────────

    def test_random_flows_never_break_the_books(self):
        for n in range(1, RUNS + 1):
            client, artist_client, customer, booking = self._new_booking(n)
            mode = self.rng.choice(['none', 'cash', 'cash', 'partial', 'full'])
            if mode != 'none':
                self._pay(client, booking, mode)
            settled = Payment.total_settled_for_booking(booking_id=booking.booking_id)
            fully_paid = settled >= booking.total_amount
            ending = self.rng.choice(['complete', 'cancel', 'abandon']) if fully_paid else self.rng.choice(['cancel', 'abandon'])
            if ending == 'complete':
                self._complete(artist_client, booking)
            elif ending == 'cancel':
                resp = client.put('/customers/bookings/cancel/', {'booking_id': booking.booking_id}, format='json')
                if resp.status_code != 200:
                    self.problems.append(f'booking {booking.booking_id}: cancel -> {resp.status_code} {resp.data}')
            self.tally[f'mode:{mode}'] += 1
            self.tally[f'end:{ending if mode != "none" or ending != "complete" else "x"}'] += 1
            self._check_everything(f'run {n} mode={mode} ending={ending} booking={booking.booking_id}')
        self.assertEqual(self.problems, [], '\n'.join(self.problems[:15]))
        # The dice must actually have reached the interesting paths, or "no problems" proves nothing.
        completed = Booking.objects.filter(status__name='completed').count()
        cancelled = Booking.objects.filter(status__name='cancelled').count()
        self.assertGreaterEqual(completed, 8, self.tally)
        self.assertGreaterEqual(cancelled, 8, self.tally)
        self.assertGreaterEqual(CoinTransaction.objects.filter(transaction_type='CASHBACK').count(), 8)
        self.assertGreaterEqual(CoinTransaction.objects.filter(transaction_type='REDEMPTION').count(), 8)
        self.assertGreaterEqual(CoinTransaction.objects.filter(transaction_type='REVERSAL').count(), 3)
        self.assertGreaterEqual(Payment.objects.filter(gateway='wallet').count(), 3)            # fully covered by coins
        self.assertGreaterEqual(Payment.objects.filter(status__name='refunded').count(), 3)
        print('SIM_COVERAGE', dict(self.tally), 'completed', completed, 'cancelled', cancelled,
              'cashback', CoinTransaction.objects.filter(transaction_type='CASHBACK').count(),
              'redemptions', CoinTransaction.objects.filter(transaction_type='REDEMPTION').count(),
              'reversals', CoinTransaction.objects.filter(transaction_type='REVERSAL').count(),
              'wallet-paid', Payment.objects.filter(gateway='wallet').count(),
              'refunded', Payment.objects.filter(status__name='refunded').count())

    # ── invariants ───────────────────────────────────────────────────────────

    def _check_everything(self, context):
        def bad(rule, detail):
            self.problems.append(f'[{context}] {rule}: {detail}')

        for wallet in CustomerWallet.objects.all():
            ledger = CoinTransaction.objects.filter(wallet=wallet)
            ledger_sum = ledger.aggregate(s=Sum('coins'))['s'] or 0
            if wallet.balance_coins != ledger_sum:
                bad('I1 balance equals ledger sum', f'wallet {wallet.customer_id}: balance {wallet.balance_coins} vs ledger {ledger_sum}')
            batch_left = ledger.filter(transaction_type__in=BATCH_TYPES, expires_at__gt=timezone.now()).aggregate(s=Sum('remaining_coins'))['s'] or 0
            if wallet.balance_coins != batch_left:
                bad('I2 balance equals unspent batches', f'wallet {wallet.customer_id}: balance {wallet.balance_coins} vs batches {batch_left}')
            for row in ledger:
                if row.balance_after < 0:
                    bad('I3 balance never negative', f'ledger row {row.transaction_id}')

        for booking in Booking.objects.all():
            fee_rate = booking.commission_rate
            expected_fee = (booking.total_amount * fee_rate / 100).quantize(Decimal('0.01'))
            if abs(booking.platform_fee - expected_fee) > Decimal('0.01') or booking.platform_fee + booking.net_amount != booking.total_amount:
                bad('I7 fee + net equals total', f'booking {booking.booking_id}: fee {booking.platform_fee} net {booking.net_amount} total {booking.total_amount}')
            settled = Payment.total_settled_for_booking(booking_id=booking.booking_id)
            if settled > booking.total_amount:
                bad('I5 never settled above total', f'booking {booking.booking_id}: settled {settled} > {booking.total_amount}')

            status = booking.status.name
            cashbacks = list(CoinTransaction.objects.filter(booking_id=booking.booking_id, transaction_type='CASHBACK'))
            expected_coins = int((booking.total_amount * self.config.cashback_percentage / Decimal('10000')
                                  / self.config.coin_value_rupees).to_integral_value(rounding=ROUND_FLOOR))
            if status == 'completed':
                if len(cashbacks) != 1 or cashbacks[0].coins != expected_coins:
                    bad('I6 completed earns exactly the cashback', f'booking {booking.booking_id}: got {[c.coins for c in cashbacks]}, expected [{expected_coins}]')
            elif cashbacks:
                bad('I6 only completed bookings earn cashback', f'booking {booking.booking_id} is {status}')

            redeemed = CoinTransaction.objects.filter(booking_id=booking.booking_id, transaction_type='REDEMPTION').aggregate(s=Sum('coins'))['s'] or 0
            reversed_ = CoinTransaction.objects.filter(booking_id=booking.booking_id, transaction_type='REVERSAL').aggregate(s=Sum('coins'))['s'] or 0
            if status in ('cancelled',) and redeemed + reversed_ != 0:
                bad('I9 cancelled booking gives all redeemed coins back', f'booking {booking.booking_id}: redeemed {redeemed} reversed {reversed_}')

            for payment in Payment.objects.filter(booking_id=booking.booking_id):
                discount = CoinTransaction.objects.filter(payment_id=payment.payment_id, transaction_type='REDEMPTION').aggregate(s=Sum('rupee_equivalent'))['s'] or Decimal('0')
                if payment.commission_amount + payment.artist_payout_amount != payment.amount + discount:
                    bad('I4 commission + payout equals the pre-discount amount',
                        f'payment {payment.payment_id}: {payment.commission_amount}+{payment.artist_payout_amount} vs {payment.amount}+{discount}')
                expected_commission = ((payment.amount + discount) * booking.commission_rate / 100).quantize(Decimal('0.01'))
                if abs(payment.commission_amount - expected_commission) > Decimal('0.01'):
                    bad('I4b commission is the booking rate on the pre-discount amount',
                        f'payment {payment.payment_id}: commission {payment.commission_amount}, expected {expected_commission}')
                if payment.status.name == 'refunded' and status != 'cancelled':
                    bad('I8 only cancelled bookings are refunded', f'payment {payment.payment_id} on {status} booking {booking.booking_id}')
                if status == 'cancelled' and payment.status.name == 'paid' and not payment.failure_reason and payment.amount > 0:
                    bad('I8 cancelled booking leaves no silently-paid payment', f'payment {payment.payment_id}')
