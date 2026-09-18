from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models import CustomerWallet, CoinTransaction, CoinConfig, RedemptionTier

from tests.test_customers import (
    make_user, make_customer, make_artist, make_sub_category, make_location_type, make_package, make_booking,
    next_weekday, seed_payment_statuses,
)


# ─── CustomerWallet.credit ──────────────────────────────────────────────────────

class WalletCreditTest(TestCase):
    def test_credit_creates_wallet_and_cashback_batch(self):
        user = make_user('+919000000500', 'customer')
        txn = CustomerWallet.credit(customer_id=user.user_id, coins=1000, transaction_type='CASHBACK')

        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 1000)
        self.assertEqual(txn.transaction_type, 'CASHBACK')
        self.assertEqual(txn.coins, 1000)
        self.assertEqual(txn.balance_after, 1000)
        self.assertEqual(txn.remaining_coins, 1000)
        self.assertIsNotNone(txn.expires_at)

    def test_credit_uses_coin_config_expiry_days(self):
        CoinConfig.objects.create(coin_expiry_days=30)
        user = make_user('+919000000501', 'customer')
        before = timezone.now()
        txn = CustomerWallet.credit(customer_id=user.user_id, coins=500, transaction_type='CASHBACK')
        self.assertAlmostEqual(
            (txn.expires_at - before).total_seconds(), timedelta(days=30).total_seconds(), delta=5,
        )

    def test_credit_adjustment_creates_a_spendable_batch(self):
        # An ADJUSTMENT credit still has to be spendable — debit() only ever draws from
        # a batch (remaining_coins), so a credit that skipped batch tracking could add
        # to balance_coins yet never actually be redeemable.
        user = make_user('+919000000502', 'customer')
        txn = CustomerWallet.credit(customer_id=user.user_id, coins=200, transaction_type='ADJUSTMENT')
        self.assertEqual(txn.remaining_coins, 200)
        self.assertIsNotNone(txn.expires_at)

    def test_credit_rejects_non_positive_amount(self):
        user = make_user('+919000000503', 'customer')
        with self.assertRaises(ValueError):
            CustomerWallet.credit(customer_id=user.user_id, coins=0, transaction_type='CASHBACK')

    def test_second_credit_accumulates_balance(self):
        user = make_user('+919000000504', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=1000, transaction_type='CASHBACK')
        CustomerWallet.credit(customer_id=user.user_id, coins=500, transaction_type='CASHBACK')
        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 1500)


# ─── CustomerWallet.debit ───────────────────────────────────────────────────────

class WalletDebitTest(TestCase):
    def test_debit_reduces_balance_and_consumes_single_batch(self):
        user = make_user('+919000000510', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=1000, transaction_type='CASHBACK')

        txn = CustomerWallet.debit(customer_id=user.user_id, coins=400, transaction_type='REDEMPTION')

        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 600)
        self.assertEqual(txn.coins, -400)
        self.assertEqual(txn.balance_after, 600)

        batch = CoinTransaction.objects.get(wallet=wallet, transaction_type='CASHBACK')
        self.assertEqual(batch.remaining_coins, 600)

    def test_debit_consumes_batches_fifo_across_multiple(self):
        user = make_user('+919000000511', 'customer')
        first = CustomerWallet.credit(customer_id=user.user_id, coins=300, transaction_type='CASHBACK')
        second = CustomerWallet.credit(customer_id=user.user_id, coins=500, transaction_type='CASHBACK')

        CustomerWallet.debit(customer_id=user.user_id, coins=400, transaction_type='REDEMPTION')

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.remaining_coins, 0)  # fully drained first (oldest)
        self.assertEqual(second.remaining_coins, 400)  # remainder drawn from the second

    def test_debit_raises_on_insufficient_balance(self):
        user = make_user('+919000000512', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=100, transaction_type='CASHBACK')
        with self.assertRaises(ValueError):
            CustomerWallet.debit(customer_id=user.user_id, coins=200, transaction_type='REDEMPTION')
        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 100)  # unchanged after the failed debit

    def test_debit_rejects_non_positive_amount(self):
        user = make_user('+919000000513', 'customer')
        with self.assertRaises(ValueError):
            CustomerWallet.debit(customer_id=user.user_id, coins=0, transaction_type='REDEMPTION')

    def test_debit_ignores_expired_batches(self):
        # Simulates a batch that has passed its expiry but hasn't been swept yet by
        # wallet.tasks.expire_lapsed_coins (it runs once/day, not instantly on expiry) —
        # balance_coins still counts it, but it must not be spendable regardless.
        user = make_user('+919000000514', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=100)
        CoinTransaction.objects.create(
            wallet=wallet, transaction_type='CASHBACK', coins=100, balance_after=100,
            remaining_coins=100, expires_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(ValueError):
            CustomerWallet.debit(customer_id=user.user_id, coins=100, transaction_type='REDEMPTION')

    def test_debit_records_rupee_equivalent_and_booking(self):
        user = make_user('+919000000515', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=5000, transaction_type='CASHBACK')
        txn = CustomerWallet.debit(
            customer_id=user.user_id, coins=5000, transaction_type='REDEMPTION', rupee_equivalent='500.00',
        )
        self.assertEqual(str(txn.rupee_equivalent), '500.00')


# ─── CustomerWallet.reverse_redemption ───────────────────────────────────────────

class WalletReversalTest(TestCase):
    def test_reverse_redemption_credits_coins_back(self):
        user = make_user('+919000000520', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=5000, transaction_type='CASHBACK')
        redemption = CustomerWallet.debit(
            customer_id=user.user_id, coins=5000, transaction_type='REDEMPTION', rupee_equivalent='500.00',
        )

        reversal = CustomerWallet.reverse_redemption(redemption_transaction_id=redemption.transaction_id)

        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 5000)
        self.assertEqual(reversal.transaction_type, 'REVERSAL')
        self.assertEqual(reversal.coins, 5000)
        self.assertEqual(reversal.reference_transaction_id, redemption.transaction_id)
        self.assertEqual(str(reversal.rupee_equivalent), '500.00')
        self.assertIsNotNone(reversal.expires_at)  # reversed coins get their own fresh expiry

    def test_reverse_redemption_twice_raises(self):
        user = make_user('+919000000521', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=1000, transaction_type='CASHBACK')
        redemption = CustomerWallet.debit(customer_id=user.user_id, coins=1000, transaction_type='REDEMPTION')

        CustomerWallet.reverse_redemption(redemption_transaction_id=redemption.transaction_id)
        with self.assertRaises(ValueError):
            CustomerWallet.reverse_redemption(redemption_transaction_id=redemption.transaction_id)

    def test_reversed_coins_are_spendable_again(self):
        user = make_user('+919000000522', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=1000, transaction_type='CASHBACK')
        redemption = CustomerWallet.debit(customer_id=user.user_id, coins=1000, transaction_type='REDEMPTION')
        CustomerWallet.reverse_redemption(redemption_transaction_id=redemption.transaction_id)

        # Should not raise — the reversal batch is a valid FIFO source.
        CustomerWallet.debit(customer_id=user.user_id, coins=1000, transaction_type='REDEMPTION')
        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 0)


# ─── RedemptionTier ─────────────────────────────────────────────────────────────

class RedemptionTierTest(TestCase):
    def test_coin_cost_computed_from_active_coin_config(self):
        CoinConfig.objects.create(coin_value_rupees='0.10')
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        self.assertEqual(tier.coin_cost, 5000)

    def test_rupee_value_not_evenly_divisible_raises(self):
        CoinConfig.objects.create(coin_value_rupees='0.30')
        with self.assertRaises(ValueError):
            RedemptionTier.objects.create(rupee_value='500.00')

    def test_get_all_active_excludes_inactive_tiers(self):
        RedemptionTier.objects.create(rupee_value='500.00')
        RedemptionTier.objects.create(rupee_value='1000.00', is_active=False)
        active = RedemptionTier.get_all_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(str(active[0]['rupee_value']), '500.00')

    def test_clean_raises_validation_error_not_bare_value_error(self):
        # clean() is what Django Admin's form validation calls (via full_clean()) —
        # it must surface as a normal field error there, not an unhandled 500.
        from django.core.exceptions import ValidationError
        CoinConfig.objects.create(coin_value_rupees='0.30')
        tier = RedemptionTier(rupee_value='500.00')
        with self.assertRaises(ValidationError):
            tier.full_clean()

    def test_negative_rupee_value_rejected_cleanly(self):
        # Regression test: a negative value that happens to divide evenly by the coin
        # value (e.g. -500.00 / 0.10 = -5000) used to sail past the divisibility check
        # and only get caught by the DB's PositiveIntegerField CHECK constraint on
        # coin_cost, surfacing as a raw, unhandled IntegrityError instead of a clean
        # business-rule error.
        from django.db import IntegrityError
        with self.assertRaises(ValueError):
            RedemptionTier.objects.create(rupee_value='-500.00')
        # Confirm it's specifically the clean ValueError path, not a bypassed
        # IntegrityError reaching the caller.
        try:
            RedemptionTier.objects.create(rupee_value='-500.00')
            self.fail('Expected an exception')
        except IntegrityError:
            self.fail('Negative rupee_value still raises a raw IntegrityError, not a clean ValueError')
        except ValueError:
            pass

    def test_zero_rupee_value_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            RedemptionTier.objects.create(rupee_value='0.00')


# ─── CoinConfig ──────────────────────────────────────────────────────────────────

class CoinConfigTest(TestCase):
    def test_get_active_creates_singleton_with_defaults(self):
        config = CoinConfig.get_active()
        self.assertEqual(config.config_id, 1)
        self.assertEqual(str(config.cashback_percentage), '10.00')

    def test_save_always_pins_pk_to_one(self):
        CoinConfig.objects.create(cashback_percentage='15.00')
        second = CoinConfig(cashback_percentage='20.00')
        second.save()
        self.assertEqual(CoinConfig.objects.count(), 1)
        self.assertEqual(str(CoinConfig.objects.get().cashback_percentage), '20.00')

    def test_zero_coin_value_rejected_by_validation(self):
        # coin_value_rupees is a divisor in award_cashback() and RedemptionTier.save() —
        # 0 would raise ZeroDivisionError the next time either runs, so full_clean()
        # (what Django Admin's form validation calls) must reject it up front.
        from django.core.exceptions import ValidationError
        config = CoinConfig(coin_value_rupees='0.0000')
        with self.assertRaises(ValidationError):
            config.full_clean()


# ─── CustomerWallet.award_cashback ───────────────────────────────────────────────

class AwardCashbackTest(TestCase):
    def test_award_cashback_converts_service_amount_to_coins(self):
        user = make_user('+919000000530', 'customer')
        txn = CustomerWallet.award_cashback(customer_id=user.user_id, booking_id=None, service_amount='1000.00')
        # 10% of 1000 = 100 rupees; at ₹0.10/coin that's 1000 coins.
        self.assertEqual(txn.coins, 1000)
        self.assertEqual(txn.transaction_type, 'CASHBACK')
        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 1000)

    def test_award_cashback_respects_custom_config(self):
        CoinConfig.objects.create(cashback_percentage='5.00', coin_value_rupees='0.50')
        user = make_user('+919000000531', 'customer')
        txn = CustomerWallet.award_cashback(customer_id=user.user_id, booking_id=None, service_amount='2000.00')
        # 5% of 2000 = 100 rupees; at ₹0.50/coin that's 200 coins.
        self.assertEqual(txn.coins, 200)

    def test_award_cashback_returns_none_when_rounds_to_zero_coins(self):
        CoinConfig.objects.create(cashback_percentage='1.00', coin_value_rupees='10.0000')
        user = make_user('+919000000532', 'customer')
        result = CustomerWallet.award_cashback(customer_id=user.user_id, booking_id=None, service_amount='1.00')
        self.assertIsNone(result)
        self.assertFalse(CustomerWallet.objects.filter(customer_id=user.user_id).exists())

    def test_second_cashback_for_same_booking_is_rejected_by_db_constraint(self):
        # Regression test for a real duplicate-cashback bug found in validation: two
        # overlapping verify_completion_pin_extract calls could each pass the (then-
        # unlocked) status/PIN checks and both credit cashback for the same booking.
        # The row-lock fix in the view is the primary defense; this DB-level
        # UniqueConstraint (unique_cashback_per_booking) is the backstop — even a
        # direct, deliberate second award_cashback() call for the same booking_id must
        # be rejected outright, never silently succeed.
        from django.db import IntegrityError
        user = make_user('+919000000533', 'customer')
        client, customer = make_customer(phone_number='+919000000534')
        _, _, profile = make_artist(phone_number='+919000000535')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )

        first = CustomerWallet.award_cashback(
            customer_id=customer.user_id, booking_id=booking.booking_id, service_amount=booking.total_amount,
        )
        self.assertIsNotNone(first)

        with self.assertRaises(IntegrityError):
            CustomerWallet.award_cashback(
                customer_id=customer.user_id, booking_id=booking.booking_id, service_amount=booking.total_amount,
            )

        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 1000)  # the failed second attempt rolled back cleanly
        self.assertEqual(
            CoinTransaction.objects.filter(booking_id=booking.booking_id, transaction_type='CASHBACK').count(), 1,
        )

    def test_racing_request_with_stale_read_is_rejected_not_double_credited(self):
        # Deterministic (non-threaded) proof of the row-lock re-validation fix in
        # ArtistBookingView.verify_completion_pin_extract: a second request whose
        # initial read overlapped with the first (and so saw the pre-completion
        # 'in_progress'/valid-PIN snapshot) must still be rejected once it reaches the
        # lock, because the actual row was already completed and the PIN already
        # nulled by the first request in the meantime.
        client, customer = make_customer(phone_number='+919000000536')
        artist_client, artist_user, profile = make_artist(phone_number='+919000000537')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='in_progress',
        )
        booking.completion_pin = 4444
        booking.completion_pin_expiry = timezone.now() + timedelta(hours=2)
        booking.save()

        stale_snapshot = Booking.get_lifecycle_state(booking_id=booking.booking_id)

        first_resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
            'booking_id': booking.booking_id, 'completion_pin': 4444,
        }, format='json')
        self.assertEqual(first_resp.status_code, 200)

        # The "racing" second request: forced to read the stale, pre-completion
        # snapshot (simulating a read that genuinely overlapped with the first,
        # before it committed), but it locks the REAL, already-completed row.
        with patch('sunndari_apps.artists.views.booking.Booking.get_lifecycle_state', return_value=stale_snapshot):
            second_resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
                'booking_id': booking.booking_id, 'completion_pin': 4444,
            }, format='json')
        self.assertEqual(second_resp.status_code, 400)

        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 1000)  # not double-credited
        self.assertEqual(
            CoinTransaction.objects.filter(booking_id=booking.booking_id, transaction_type='CASHBACK').count(), 1,
        )


# ─── Cashback integration at booking completion ──────────────────────────────────

class CashbackCompletionIntegrationTest(TestCase):
    """Confirms the wiring in ArtistBookingView.verify_completion_pin_extract — that a
    wallet-credit failure rolls back the booking completion itself (Completion PIN
    stays valid for the artist to retry) rather than silently losing the cashback."""

    def _make_in_progress_booking(self, customer_phone, artist_phone, price=1000):
        customer_client, customer = make_customer(phone_number=customer_phone)
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=(timezone.now() + timedelta(days=1)).date(),
            start_time='10:00:00', end_time='11:00:00', status_name='in_progress',
        )
        booking.completion_pin = 4321
        booking.completion_pin_expiry = timezone.now() + timedelta(hours=2)
        booking.save()
        return artist_client, customer, booking

    def test_successful_completion_credits_cashback(self):
        artist_client, customer, booking = self._make_in_progress_booking(
            '+919000000540', '+919000000541', price=1000,
        )
        resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
            'booking_id': booking.booking_id, 'completion_pin': 4321,
        }, format='json')
        self.assertEqual(resp.status_code, 200)

        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'completed')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 1000)

    def test_cashback_failure_rolls_back_booking_completion(self):
        artist_client, customer, booking = self._make_in_progress_booking(
            '+919000000542', '+919000000543', price=1000,
        )
        with patch(
            'sunndari_apps.artists.views.booking.CustomerWallet.award_cashback',
            side_effect=RuntimeError('wallet boom'),
        ):
            resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
                'booking_id': booking.booking_id, 'completion_pin': 4321,
            }, format='json')
        self.assertEqual(resp.status_code, 400)

        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')  # not completed — rolled back
        self.assertEqual(booking.completion_pin, 4321)  # PIN not consumed, artist can retry
        self.assertFalse(CoinTransaction.objects.filter(booking_id=booking.booking_id).exists())
        self.assertFalse(CustomerWallet.objects.filter(customer_id=customer.user_id).exists())

    def test_lock_contention_returns_clean_retry_message_not_raw_db_error(self):
        # Regression test: a lock-contention error (SQLite's "database is locked"
        # under concurrent requests, or a Postgres lock-timeout/serialization
        # failure) used to fall through to Common().exception_handler's generic
        # branch and surface as an opaque "Database Error". It must instead be a
        # clean, retry-friendly ValueError, with the transaction rolled back cleanly
        # (booking untouched, PIN still valid) so an immediate retry succeeds.
        from django.db import OperationalError
        artist_client, customer, booking = self._make_in_progress_booking(
            '+919000000544', '+919000000545', price=1000,
        )
        with patch(
            'sunndari_apps.artists.views.booking.CustomerWallet.award_cashback',
            side_effect=OperationalError('database is locked'),
        ):
            resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
                'booking_id': booking.booking_id, 'completion_pin': 4321,
            }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('busy', resp.data['message'].lower())

        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')
        self.assertEqual(booking.completion_pin, 4321)

        retry_resp = artist_client.put('/artists/bookings/completion_pin/verify/', {
            'booking_id': booking.booking_id, 'completion_pin': 4321,
        }, format='json')
        self.assertEqual(retry_resp.status_code, 200)


# ─── Eligible redemption tiers ───────────────────────────────────────────────────

class EligibleTiersEndpointTest(TestCase):
    url = '/customers/wallet/eligible_tiers/'

    def _make_booking(self, customer_phone, artist_phone, price=2000):
        client, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return client, customer, booking

    def test_returns_only_affordable_and_in_range_tiers(self):
        RedemptionTier.objects.create(rupee_value='500.00')   # 5000 coins
        RedemptionTier.objects.create(rupee_value='1000.00')  # 10000 coins
        RedemptionTier.objects.create(rupee_value='3000.00')  # 30000 coins, exceeds booking amount
        client, customer, booking = self._make_booking('+919000000550', '+919000000551', price=2000)
        CustomerWallet.credit(customer_id=customer.user_id, coins=6000, transaction_type='ADJUSTMENT')

        resp = client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        values = {str(item['rupeeValue']) for item in resp.data['data']}
        # ₹1000 tier needs 10,000 coins (only 6,000 available) -> excluded.
        # ₹3000 tier exceeds the ₹2000 booking amount -> excluded.
        self.assertEqual(values, {'500.00'})

    def test_wrong_customer_returns_400(self):
        client, customer, booking = self._make_booking('+919000000552', '+919000000553', price=2000)
        outsider_client, _ = make_customer(phone_number='+919000000554')
        resp = outsider_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_no_wallet_yet_returns_empty_list_not_error(self):
        RedemptionTier.objects.create(rupee_value='500.00')
        client, customer, booking = self._make_booking('+919000000555', '+919000000556', price=2000)
        resp = client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data'], [])


# ─── Redemption integration at payment initiation ────────────────────────────────

class RedemptionAtInitiateTest(TestCase):
    initiate_url = '/customers/payments/initiate/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_get_client.return_value = mock_client
        self.mock_razorpay_client = mock_client

    def _make_booking(self, customer_phone, artist_phone, price=2000, commission_rate=None):
        client, customer = make_customer(phone_number=customer_phone)
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
        return client, customer, profile, booking

    def test_redemption_reduces_charge_and_debits_coins(self):
        seed_payment_statuses()
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # 5000 coins
        client, customer, profile, booking = self._make_booking(
            '+919000000560', '+919000000561', price=2000, commission_rate='10.00',
        )
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['coins_redeemed'], 5000)
        self.assertEqual(str(resp.data['data']['redemption_discount']), '500.00')
        # ₹2000 - ₹500 redeemed = ₹1500 actually charged -> 150000 paise.
        self.assertEqual(resp.data['data']['amount'], 150000)

        payment = Payment.objects.get(payment_id=resp.data['data']['payment_id'])
        self.assertEqual(str(payment.amount), '1500.00')
        # Commission/payout computed on the PRE-redemption ₹2000, not the discounted
        # ₹1500 — confirms the platform (not the artist) absorbs the redemption discount.
        self.assertEqual(str(payment.commission_amount), '200.00')
        self.assertEqual(str(payment.artist_payout_amount), '1800.00')

        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)
        redemption_txn = CoinTransaction.objects.get(wallet=wallet, transaction_type='REDEMPTION')
        self.assertEqual(redemption_txn.coins, -5000)
        self.assertEqual(redemption_txn.booking_id, booking.booking_id)
        self.assertEqual(redemption_txn.payment_id, payment.payment_id)
        self.assertEqual(str(redemption_txn.rupee_equivalent), '500.00')

    def test_inactive_tier_returns_400_and_touches_no_coins(self):
        seed_payment_statuses()
        tier = RedemptionTier.objects.create(rupee_value='500.00', is_active=False)
        client, customer, profile, booking = self._make_booking('+919000000562', '+919000000563', price=2000)
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 5000)  # untouched

    def test_tier_exceeding_amount_is_blocked(self):
        seed_payment_statuses()
        tier = RedemptionTier.objects.create(rupee_value='3000.00')  # exceeds the ₹2000 booking
        client, customer, profile, booking = self._make_booking('+919000000564', '+919000000565', price=2000)
        CustomerWallet.credit(customer_id=customer.user_id, coins=30000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 30000)  # untouched

    def test_insufficient_coins_marks_payment_failed(self):
        seed_payment_statuses()
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # needs 5000 coins
        client, customer, profile, booking = self._make_booking('+919000000566', '+919000000567', price=2000)
        CustomerWallet.credit(customer_id=customer.user_id, coins=100, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        # The gateway order WAS created (the failure is only discovered after) — the
        # payment attempt built on top of it must be recorded as failed, not left pending.
        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'failed')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 100)  # untouched

    def test_no_redemption_tier_behaves_exactly_as_before(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking('+919000000568', '+919000000569', price=2000)
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn('coins_redeemed', resp.data['data'])
        payment = Payment.objects.get(payment_id=resp.data['data']['payment_id'])
        self.assertEqual(str(payment.amount), '2000.00')

    def test_lock_contention_during_debit_returns_clean_retry_message(self):
        # Regression test: a lock-contention error during the redemption debit used to
        # fall through to Common().exception_handler's generic branch as an opaque
        # "Database Error". It must instead be a clean, retry-friendly ValueError, and
        # the payment must be marked failed (not left dangling in 'pending').
        from django.db import OperationalError
        seed_payment_statuses()
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        client, customer, profile, booking = self._make_booking('+919000000570', '+919000000571', price=2000)
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        with patch(
            'sunndari_apps.payments.views.initiate_payment.CustomerWallet.debit',
            side_effect=OperationalError('database is locked'),
        ):
            resp = client.post(self.initiate_url, {
                'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
            }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('busy', resp.data['message'].lower())

        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'failed')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 5000)  # untouched


# ─── Redemption reversal on booking cancellation ─────────────────────────────────

class RedemptionReversalOnCancelTest(TestCase):
    initiate_url = '/customers/payments/initiate/'
    cancel_url = '/customers/bookings/cancel/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_get_client.return_value = mock_client

    def _make_booking_with_redemption(self, customer_phone, artist_phone, price=2000):
        seed_payment_statuses()
        client, customer = make_customer(phone_number=customer_phone)
        artist_client, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # 5000 coins
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')
        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        return client, artist_client, customer, booking, tier

    def test_cancelling_pending_booking_reverses_redemption(self):
        client, artist_client, customer, booking, tier = self._make_booking_with_redemption('+919000000570', '+919000000571')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)  # spent on redemption

        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id, 'reason': 'changed my mind'}, format='json')
        self.assertEqual(resp.status_code, 200)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 5000)  # coins returned
        reversal = CoinTransaction.objects.get(wallet=wallet, transaction_type='REVERSAL')
        self.assertEqual(reversal.coins, 5000)
        redemption = CoinTransaction.objects.get(wallet=wallet, transaction_type='REDEMPTION')
        self.assertEqual(reversal.reference_transaction_id, redemption.transaction_id)

    def test_cancelling_paid_confirmed_booking_reverses_redemption_and_refunds_payment(self):
        client, artist_client, customer, booking, tier = self._make_booking_with_redemption('+919000000572', '+919000000573')
        # Move straight to 'confirmed' with the redeemed payment marked 'paid', mirroring
        # test_cancel_paid_confirmed_booking_triggers_refund in tests/test_customers.py.
        payment = Payment.objects.get(booking_id=booking.booking_id)
        payment.status = PaymentStatus.objects.get(name='paid')
        payment.save()
        booking.status = BookingStatus.objects.get(name='confirmed')
        booking.save()

        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id, 'reason': 'changed my mind'}, format='json')
        self.assertEqual(resp.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status.name, 'refunded')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 5000)

    def test_cancelling_twice_does_not_double_reverse(self):
        client, artist_client, customer, booking, tier = self._make_booking_with_redemption('+919000000574', '+919000000575')
        client.put(self.cancel_url, {'booking_id': booking.booking_id}, format='json')
        second_resp = client.put(self.cancel_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(second_resp.status_code, 400)  # already cancelled — blocked before reaching reversal again
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 5000)  # not double-credited

    def test_artist_rejecting_pending_booking_also_reverses_redemption(self):
        # Same reversal, via the OTHER call site that refunds a payment on cancellation
        # — ArtistBookingView.update_status_extract (artist rejects/cancels), not just
        # the customer-initiated BookingView.cancel_extract path above.
        client, artist_client, customer, booking, tier = self._make_booking_with_redemption('+919000000598', '+919000000599')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)  # spent on redemption

        resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'cancelled',
        }, format='json')
        self.assertEqual(resp.status_code, 200)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 5000)  # coins returned
        self.assertTrue(CoinTransaction.objects.filter(wallet=wallet, transaction_type='REVERSAL').exists())

    def test_cancelling_booking_without_redemption_is_unaffected(self):
        client, customer = make_customer(phone_number='+919000000576')
        _, _, profile = make_artist(phone_number='+919000000577')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomerWallet.objects.filter(customer_id=customer.user_id).exists())


# ─── Customer-facing wallet balance / transaction history APIs ──────────────────

class WalletBalanceEndpointTest(TestCase):
    url = '/customers/wallet/get/'

    def test_new_customer_gets_zero_balance_not_404(self):
        client, customer = make_customer(phone_number='+919000000580')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['balanceCoins'], 0)
        self.assertEqual(resp.data['data']['customerId'], customer.user_id)
        self.assertTrue(CustomerWallet.objects.filter(customer_id=customer.user_id).exists())

    def test_balance_reflects_credits(self):
        client, customer = make_customer(phone_number='+919000000581')
        CustomerWallet.credit(customer_id=customer.user_id, coins=1234, transaction_type='ADJUSTMENT')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['balanceCoins'], 1234)

    def test_unauthenticated_returns_401(self):
        from rest_framework.test import APIClient
        resp = APIClient().get(self.url)
        self.assertEqual(resp.status_code, 401)


class WalletTransactionsEndpointTest(TestCase):
    url = '/customers/wallet/transactions/'

    def test_lists_own_transactions_only(self):
        client, customer = make_customer(phone_number='+919000000582')
        other_client, other_customer = make_customer(phone_number='+919000000583')
        CustomerWallet.credit(customer_id=customer.user_id, coins=500, transaction_type='ADJUSTMENT')
        CustomerWallet.credit(customer_id=other_customer.user_id, coins=999, transaction_type='ADJUSTMENT')

        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['data']['data']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['coins'], 500)
        self.assertEqual(rows[0]['transactionType'], 'ADJUSTMENT')

    def test_empty_history_for_new_customer(self):
        client, customer = make_customer(phone_number='+919000000584')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'], [])
        self.assertEqual(resp.data['data']['presentPage'], 1)

    def test_transactions_ordered_most_recent_first(self):
        client, customer = make_customer(phone_number='+919000000585')
        CustomerWallet.credit(customer_id=customer.user_id, coins=100, transaction_type='ADJUSTMENT')
        CustomerWallet.credit(customer_id=customer.user_id, coins=200, transaction_type='ADJUSTMENT')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        coins_in_order = [row['coins'] for row in resp.data['data']['data']]
        self.assertEqual(coins_in_order, [200, 100])


# ─── Periodic expiry sweep (wallet.tasks.expire_lapsed_coins) ────────────────────

class ExpireLapsedCoinsTest(TestCase):
    def test_sweeps_a_lapsed_batch_and_decrements_balance(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000590', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=1000)
        batch = CoinTransaction.objects.create(
            wallet=wallet, transaction_type='CASHBACK', coins=1000, balance_after=1000,
            remaining_coins=1000, expires_at=timezone.now() - timedelta(days=1),
        )

        expired_count = expire_lapsed_coins()
        self.assertEqual(expired_count, 1)

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 0)
        batch.refresh_from_db()
        self.assertEqual(batch.remaining_coins, 0)
        expiry_txn = CoinTransaction.objects.get(wallet=wallet, transaction_type='EXPIRY')
        self.assertEqual(expiry_txn.coins, -1000)
        self.assertEqual(expiry_txn.balance_after, 0)
        self.assertEqual(expiry_txn.reference_transaction_id, batch.transaction_id)

    def test_partially_spent_batch_only_expires_the_remainder(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000591', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=400)
        CoinTransaction.objects.create(
            wallet=wallet, transaction_type='CASHBACK', coins=1000, balance_after=1000,
            remaining_coins=400,  # 600 already spent via a prior debit()
            expires_at=timezone.now() - timedelta(days=1),
        )

        expire_lapsed_coins()
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 0)  # only the unspent 400 is swept

    def test_unexpired_batch_is_untouched(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000592', 'customer')
        CustomerWallet.credit(customer_id=user.user_id, coins=500, transaction_type='CASHBACK')

        expired_count = expire_lapsed_coins()
        self.assertEqual(expired_count, 0)
        wallet = CustomerWallet.objects.get(customer_id=user.user_id)
        self.assertEqual(wallet.balance_coins, 500)

    def test_fully_spent_expired_batch_is_skipped(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000593', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=0)
        CoinTransaction.objects.create(
            wallet=wallet, transaction_type='CASHBACK', coins=1000, balance_after=1000,
            remaining_coins=0,  # fully spent already
            expires_at=timezone.now() - timedelta(days=1),
        )
        expired_count = expire_lapsed_coins()
        self.assertEqual(expired_count, 0)
        self.assertFalse(CoinTransaction.objects.filter(wallet=wallet, transaction_type='EXPIRY').exists())

    def test_running_twice_does_not_double_expire(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000594', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=500)
        CoinTransaction.objects.create(
            wallet=wallet, transaction_type='CASHBACK', coins=500, balance_after=500,
            remaining_coins=500, expires_at=timezone.now() - timedelta(days=1),
        )

        first = expire_lapsed_coins()
        second = expire_lapsed_coins()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 0)
        self.assertEqual(CoinTransaction.objects.filter(wallet=wallet, transaction_type='EXPIRY').count(), 1)

    def test_expired_reversal_batch_is_also_swept(self):
        # REVERSAL is a BATCH_TRANSACTION_TYPES type too — coins returned via
        # reverse_redemption() must expire the same as an original CASHBACK batch.
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user = make_user('+919000000595', 'customer')
        wallet = CustomerWallet.objects.create(customer_id=user.user_id, balance_coins=200)
        CoinTransaction.objects.create(
            wallet=wallet, transaction_type='REVERSAL', coins=200, balance_after=200,
            remaining_coins=200, expires_at=timezone.now() - timedelta(days=1),
        )
        expired_count = expire_lapsed_coins()
        self.assertEqual(expired_count, 1)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_coins, 0)

    def test_sweeps_multiple_customers_independently(self):
        from sunndari_apps.wallet.tasks import expire_lapsed_coins

        user_a = make_user('+919000000596', 'customer')
        user_b = make_user('+919000000597', 'customer')
        wallet_a = CustomerWallet.objects.create(customer_id=user_a.user_id, balance_coins=100)
        wallet_b = CustomerWallet.objects.create(customer_id=user_b.user_id, balance_coins=300)
        CoinTransaction.objects.create(
            wallet=wallet_a, transaction_type='CASHBACK', coins=100, balance_after=100,
            remaining_coins=100, expires_at=timezone.now() - timedelta(days=1),
        )
        CoinTransaction.objects.create(
            wallet=wallet_b, transaction_type='CASHBACK', coins=300, balance_after=300,
            remaining_coins=300, expires_at=timezone.now() - timedelta(days=1),
        )

        expired_count = expire_lapsed_coins()
        self.assertEqual(expired_count, 2)
        wallet_a.refresh_from_db()
        wallet_b.refresh_from_db()
        self.assertEqual(wallet_a.balance_coins, 0)
        self.assertEqual(wallet_b.balance_coins, 0)


# ─── Redemption reversal on the auto-expiry sweep (abandoned checkout) ───────────

class RedemptionReversalOnAutoExpiryTest(TestCase):
    """Regression test for a real bug found in validation: cancel_stale_pending_bookings
    (the Celery sweep that auto-cancels a stale 'pending' booking) used a bulk
    QuerySet.update() with zero side effects, so a customer who redeemed coins at
    /initiate/ and then simply abandoned checkout would permanently lose those coins
    once the sweep ran — unlike the customer- and artist-initiated cancellation paths,
    which already reverse them."""

    initiate_url = '/customers/payments/initiate/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        mock_client = MagicMock()
        mock_client.order.create.side_effect = lambda data: {
            'id': f"order_test_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        mock_get_client.return_value = mock_client

    def test_auto_expiry_sweep_reverses_redeemed_coins(self):
        from sunndari_apps.customers.tasks import cancel_stale_pending_bookings

        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000600')
        _, _, profile = make_artist(phone_number='+919000000601')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # 5000 coins
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)  # spent on redemption

        # Customer never calls /verify/ — payment stays 'pending' forever. Simulate the
        # slot-lock window elapsing, then run the real Celery task.
        Booking.objects.filter(booking_id=booking.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancelled_count = cancel_stale_pending_bookings()

        booking.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(cancelled_count, 1)
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertEqual(wallet.balance_coins, 5000)  # coins returned
        self.assertTrue(CoinTransaction.objects.filter(wallet=wallet, transaction_type='REVERSAL').exists())

    def test_auto_expiry_sweep_unaffected_without_redemption(self):
        from sunndari_apps.customers.tasks import cancel_stale_pending_bookings

        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000602')
        _, _, profile = make_artist(phone_number='+919000000603')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        Booking.objects.filter(booking_id=booking.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))

        cancelled_count = cancel_stale_pending_bookings()
        self.assertEqual(cancelled_count, 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertFalse(CustomerWallet.objects.filter(customer_id=customer.user_id).exists())


# ─── Settled-value calculation (cash + redeemed coins) ───────────────────────────

class TotalSettledForBookingTest(TestCase):
    """Regression tests for a real bug found in validation: Payment.total_paid_for_booking()
    only summed cash paid, ignoring redeemed coin value — so any booking whose settling
    payment used redemption could never be confirmed by the artist, even though the
    customer paid everything owed (cash + coins)."""

    initiate_url = '/customers/payments/initiate/'
    verify_url = '/customers/payments/verify/'
    confirm_url = '/artists/bookings/update_status/'

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

    def _pay_with_redemption(self, client, booking, tier):
        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        order_id = resp.data['data']['gateway_order_id']
        amount_paise = resp.data['data']['amount']
        self.mock_razorpay_client.payment.fetch.return_value = {
            'id': 'pay_test', 'order_id': order_id, 'status': 'captured', 'amount': amount_paise,
        }
        self.mock_razorpay_client.order.fetch.return_value = {
            'id': order_id, 'amount': amount_paise, 'amount_paid': amount_paise,
            'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        verify_resp = client.post(self.verify_url, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_test', 'razorpay_signature': 'sig_ok',
        }, format='json')
        self.assertEqual(verify_resp.status_code, 200)

    def test_settled_value_includes_redeemed_coins(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000700')
        _, _, profile = make_artist(phone_number='+919000000701')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        self._pay_with_redemption(client, booking, tier)

        # ₹1500 cash + ₹500 redeemed = ₹2000, matching the booking's full total_amount.
        self.assertEqual(Payment.total_settled_for_booking(booking_id=booking.booking_id), Decimal('2000.00'))

    def test_artist_can_confirm_booking_settled_partly_by_coins(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000702')
        artist_client, artist_user, profile = make_artist(phone_number='+919000000703')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        self._pay_with_redemption(client, booking, tier)

        confirm_resp = artist_client.put(self.confirm_url, {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'confirmed')

    def test_unpaid_redemption_does_not_count_as_settled(self):
        # A redemption tied to a payment that never succeeded (still 'pending') must
        # NOT count toward the booking's settled total.
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000704')
        _, _, profile = make_artist(phone_number='+919000000705')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=2000)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        # Never call /verify/ — payment stays 'pending'.

        self.assertEqual(Payment.total_settled_for_booking(booking_id=booking.booking_id), 0)


# ─── Fully-covered-by-coins payment (gateway skip) ───────────────────────────────

class FullyCoveredByCoinsTest(TestCase):
    initiate_url = '/customers/payments/initiate/'
    confirm_url = '/artists/bookings/update_status/'

    def setUp(self):
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        mock_get_client = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_razorpay_client = MagicMock()
        mock_get_client.return_value = self.mock_razorpay_client

    def test_fully_covered_booking_skips_gateway_and_settles_directly(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000706')
        artist_client, artist_user, profile = make_artist(phone_number='+919000000707')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=500)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')  # exactly covers the booking
        CustomerWallet.credit(customer_id=customer.user_id, coins=5000, transaction_type='ADJUSTMENT')

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['data']['fully_covered_by_coins'])
        self.assertEqual(resp.data['data']['amount'], 0)
        self.assertEqual(resp.data['data']['coins_redeemed'], 5000)
        self.mock_razorpay_client.order.create.assert_not_called()

        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'paid')
        self.assertEqual(payment.gateway, 'wallet')
        self.assertIsNone(payment.gateway_order_id)
        self.assertEqual(str(payment.amount), '0.00')
        self.assertIsNotNone(payment.paid_at)

        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 0)

        confirm_resp = artist_client.put(self.confirm_url, {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)

    def test_insufficient_coins_for_full_coverage_marks_failed_no_gateway_call(self):
        seed_payment_statuses()
        client, customer = make_customer(phone_number='+919000000708')
        _, _, profile = make_artist(phone_number='+919000000709')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=500)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        tier = RedemptionTier.objects.create(rupee_value='500.00')
        CustomerWallet.credit(customer_id=customer.user_id, coins=100, transaction_type='ADJUSTMENT')  # not enough

        resp = client.post(self.initiate_url, {
            'booking_id': booking.booking_id, 'redemption_tier_id': tier.tier_id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.mock_razorpay_client.order.create.assert_not_called()
        payment = Payment.objects.get(booking_id=booking.booking_id)
        self.assertEqual(payment.status.name, 'failed')
        wallet = CustomerWallet.objects.get(customer_id=customer.user_id)
        self.assertEqual(wallet.balance_coins, 100)  # untouched
