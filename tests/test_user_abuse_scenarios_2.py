"""Second round of ways real users push on the system, each pinned by a test that asserts the SAFE
outcome — a failure here is a real hole, not a test quirk.

6. Spending the same coins twice (two bookings, one balance; cancelling twice; someone else's booking).
7. An artist acting out of turn (confirming unpaid work, skipping the arrival/PIN steps, guessing PINs,
   or a customer/artist calling endpoints that belong to another role).
8. An artist tampering with another artist's packages, add-ons or bookings.
9. Review and rating abuse (not completed, twice, out-of-range ratings, replying to a rival's review).
10. Hostile query strings and bodies (pagination extremes, sort/filter on secret columns, non-object
    JSON, injection strings, asking for secret columns by name).
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from sunndari_apps.artists.models import ArtistProfile, PackageAddOn, PricingPackage
from sunndari_apps.core.models import BookingStatus
from sunndari_apps.core.models.brand import Brand
from sunndari_apps.customers.models import Booking, Review
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models import CoinConfig, CoinTransaction, CustomerWallet, RedemptionTier

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type, make_package, make_booking,
    make_paid_payment, next_weekday,
)
from tests.test_user_abuse_scenarios import MarketplaceMixin


def set_status(booking, name, **fields):
    Booking.objects.filter(booking_id=booking.booking_id).update(
        status=BookingStatus.objects.get(name=name), **fields,
    )
    booking.refresh_from_db()


# ─── 6. Spending the same coins twice ─────────────────────────────────────────

class CoinAbuseTest(MarketplaceMixin, TestCase):
    INITIATE = '/customers/payments/initiate/'

    def setUp(self):
        super().setUp()
        CoinConfig.objects.create(coin_value_rupees='0.10')
        client_mock = MagicMock()
        client_mock.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        patcher = patch(
            'sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=client_mock,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tier = RedemptionTier.objects.create(rupee_value='500.00')        # costs 5000 coins
        self.client, self.customer = make_customer(phone_number='+919100000601')
        CustomerWallet.credit(customer_id=self.customer.user_id, coins=5000, transaction_type='ADJUSTMENT')
        self.first = self.book(self.client, start='10:00:00').data['data']['booking_id']
        self.second = self.book(self.client, start='15:00:00').data['data']['booking_id']

    def _balance(self):
        return CustomerWallet.objects.get(customer_id=self.customer.user_id).balance_coins

    def _redeem(self, booking_id, tier_id=None, client=None):
        return (client or self.client).post(self.INITIATE, {
            'booking_id': booking_id, 'redemption_tier_id': tier_id or self.tier.tier_id,
        }, format='json')

    def test_one_balance_cannot_pay_for_two_redemptions(self):
        self.assertEqual(self._redeem(self.first).status_code, 201)
        self.assertEqual(self._balance(), 0)
        self.assertEqual(self._redeem(self.second).status_code, 400)
        self.assertEqual(self._balance(), 0)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='REDEMPTION').count(), 1)

    def test_cancelling_twice_returns_the_coins_only_once(self):
        self._redeem(self.first)
        cancel = lambda: self.client.put('/customers/bookings/cancel/', {'booking_id': self.first}, format='json')
        self.assertEqual(cancel().status_code, 200)
        self.assertEqual(cancel().status_code, 400)
        self.assertEqual(self._balance(), 5000)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='REVERSAL').count(), 1)

    def test_coins_cannot_be_spent_on_someone_elses_booking(self):
        stranger_client, stranger = make_customer(phone_number='+919100000602')
        CustomerWallet.credit(customer_id=stranger.user_id, coins=5000, transaction_type='ADJUSTMENT')
        resp = self._redeem(self.first, client=stranger_client)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CustomerWallet.objects.get(customer_id=stranger.user_id).balance_coins, 5000)

    def test_unknown_or_inactive_tiers_touch_no_coins(self):
        inactive = RedemptionTier.objects.create(rupee_value='100.00', is_active=False)
        for tier_id in (inactive.tier_id, 99999):
            self.assertEqual(self._redeem(self.first, tier_id=tier_id).status_code, 400)
        self.assertEqual(self._balance(), 5000)
        self.assertEqual(CoinTransaction.objects.filter(transaction_type='REDEMPTION').count(), 0)


# ─── 7. An artist (or wrong role) acting out of turn ──────────────────────────

class OutOfTurnActionsTest(MarketplaceMixin, TestCase):
    STATUS = '/artists/bookings/update_status/'

    def setUp(self):
        super().setUp()
        self.customer_client, self.customer = make_customer(phone_number='+919100000701')
        self.booking_id = self.book(self.customer_client).data['data']['booking_id']
        self.booking = Booking.objects.get(booking_id=self.booking_id)

    def _state(self):
        return Booking.objects.get(booking_id=self.booking_id)

    def test_artist_cannot_confirm_work_the_customer_has_not_paid_for(self):
        resp = self.artist_client.put(self.STATUS, {'booking_id': self.booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._state().status.name, 'pending')

    def test_a_different_artist_cannot_touch_the_booking(self):
        rival_client, _, _ = make_artist(phone_number='+919100000702')
        make_paid_payment(self.booking)
        for new_status in ('confirmed', 'cancelled', 'no_show'):
            resp = rival_client.put(self.STATUS, {'booking_id': self.booking_id, 'status': new_status}, format='json')
            self.assertEqual(resp.status_code, 400, new_status)
        self.assertEqual(self._state().status.name, 'pending')
        self.assertEqual(rival_client.get('/artists/bookings/get/', {'booking_id': self.booking_id}).status_code, 400)

    def test_service_steps_cannot_be_skipped(self):
        make_paid_payment(self.booking)
        set_status(self.booking, 'confirmed')
        verify_start = lambda pin: self.artist_client.put(
            '/artists/bookings/start_pin/verify/', {'booking_id': self.booking_id, 'start_service_pin': pin}, format='json')
        verify_done = lambda pin: self.artist_client.put(
            '/artists/bookings/completion_pin/verify/', {'booking_id': self.booking_id, 'completion_pin': pin}, format='json')
        self.assertEqual(verify_start(1234).status_code, 400)                    # never arrived
        self.assertEqual(verify_done(1234).status_code, 400)                     # never started
        self.assertEqual(self.artist_client.put(
            '/artists/bookings/completion_pin/request/', {'booking_id': self.booking_id}, format='json').status_code, 400)
        self.assertEqual(self.artist_client.put(
            '/artists/bookings/arrived/', {'booking_id': self.booking_id}, format='json').status_code, 400)  # no on-my-way
        self.assertEqual(self._state().status.name, 'confirmed')

    def test_guessing_the_start_pin_locks_out_even_the_right_pin(self):
        now = timezone.now()
        set_status(
            self.booking, 'confirmed', on_my_way_at=now, arrived_at=now,
            start_service_pin=4321, start_pin_expiry=now + timedelta(hours=1),
        )
        for guess in (1111, 2222, 3333, 4444, 5555, 6666, 7777):
            self.artist_client.put('/artists/bookings/start_pin/verify/',
                                   {'booking_id': self.booking_id, 'start_service_pin': guess}, format='json')
        resp = self.artist_client.put('/artists/bookings/start_pin/verify/',
                                      {'booking_id': self.booking_id, 'start_service_pin': 4321}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._state().status.name, 'confirmed')

    def test_the_customer_never_gets_to_set_the_service_pins(self):
        for url in ('/customers/bookings/start_pin/', '/customers/bookings/completion_pin/'):
            self.assertNotEqual(self.customer_client.put(url, {'booking_id': self.booking_id, 'start_service_pin': 1}, format='json').status_code, 200)
        self.assertIsNone(self._state().service_started_at)

    def test_a_customer_account_cannot_use_artist_endpoints(self):
        before = PricingPackage.objects.count()
        calls = [
            self.customer_client.get('/artists/bookings/get_all/'),
            self.customer_client.put(self.STATUS, {'booking_id': self.booking_id, 'status': 'confirmed'}, format='json'),
            self.customer_client.post('/artists/packages/create/', {
                'sub_category_id': self.package.sub_category_id, 'name': 'Mine now', 'price': '999', 'duration_minutes': 60,
            }, format='json'),
        ]
        for resp in calls:
            self.assertNotIn(resp.status_code, (200, 201))
        self.assertEqual(PricingPackage.objects.count(), before)

    def test_customer_and_artist_accounts_cannot_use_admin_endpoints(self):
        for client in (self.customer_client, self.artist_client):
            resp = client.post('/admin-panel/brands/create/', {'name': 'Hijacked Brand'}, format='json')
            self.assertNotIn(resp.status_code, (200, 201))
        self.assertFalse(Brand.objects.filter(name='Hijacked Brand').exists())


# ─── 8. An artist tampering with a rival's data ───────────────────────────────

class RivalTamperingTest(TestCase):

    def setUp(self):
        self.rival_client, _, self.rival = make_artist(phone_number='+919100000801')
        _, _, self.victim = make_artist(phone_number='+919100000802')
        self.package = make_package(self.victim, sub_category=make_sub_category(), price=1500, duration=60)
        self.addon = PackageAddOn.objects.create(artist=self.victim, name='Hair styling', price=Decimal('500'), duration_minutes=30)

    def test_cannot_edit_a_rivals_package(self):
        resp = self.rival_client.put('/artists/packages/update/', {
            'package_id': self.package.package_id, 'name': 'Hacked', 'price': '500', 'is_active': False,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.package.refresh_from_db()
        self.assertEqual((self.package.name, self.package.price, self.package.is_active), ('Basic Package', Decimal('1500.00'), True))

    def test_cannot_delete_a_rivals_package(self):
        resp = self.rival_client.delete('/artists/packages/delete/', {'package_id': self.package.package_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(PricingPackage.objects.filter(package_id=self.package.package_id).exists())

    def test_cannot_edit_a_rivals_addon(self):
        resp = self.rival_client.put('/artists/addons/update/', {
            'addon_id': self.addon.addon_id, 'name': 'Hacked', 'price': '1',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.addon.refresh_from_db()
        self.assertEqual((self.addon.name, self.addon.price), ('Hair styling', Decimal('500.00')))

    def test_cannot_attach_a_rivals_package_to_own_addon(self):
        own_addon = PackageAddOn.objects.create(artist=self.rival, name='Own', price=Decimal('100'), duration_minutes=15)
        resp = self.rival_client.put('/artists/addons/update/', {
            'addon_id': own_addon.addon_id, 'package_ids': [self.package.package_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(own_addon.packages.filter(package_id=self.package.package_id).exists())

    def test_cannot_list_or_read_a_rivals_resources_through_own_lists(self):
        packages = self.rival_client.get('/artists/packages/get_all/')
        self.assertNotIn(self.package.package_id, [p['packageId'] for p in packages.data['data']['data']])
        self.assertEqual(self.rival_client.get('/artists/packages/get/', {'package_id': self.package.package_id}).status_code, 400)
        self.assertEqual(self.rival_client.get('/artists/addons/get/', {'addon_id': self.addon.addon_id}).status_code, 400)

    def test_package_price_floor_cannot_be_dodged_by_editing(self):
        own_client, _, own = make_artist(phone_number='+919100000803')
        own_package = make_package(own, sub_category=make_sub_category(), price=1500, duration=60)
        for price in ('1', '-5', '0', '499.99'):
            resp = own_client.put('/artists/packages/update/', {'package_id': own_package.package_id, 'price': price}, format='json')
            self.assertEqual(resp.status_code, 400, price)
        own_package.refresh_from_db()
        self.assertEqual(own_package.price, Decimal('1500.00'))


# ─── 9. Review and rating abuse ───────────────────────────────────────────────

class ReviewAbuseTest(TestCase):
    REVIEW = '/customers/reviews/create/'

    def setUp(self):
        self.customer_client, self.customer = make_customer(phone_number='+919100000901')
        self.artist_client, _, self.profile = make_artist(phone_number='+919100000902')
        package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=60)
        self.location = make_location_type()
        self.pending = make_booking(self.customer, self.profile, package, self.location,
                                    booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00')
        self.done = make_booking(self.customer, self.profile, package, self.location,
                                 booking_date=next_weekday(3), start_time='10:00:00', end_time='11:00:00', status_name='completed')

    def _rate(self, booking, rating, comment=''):
        return self.customer_client.post(self.REVIEW, {'booking_id': booking.booking_id, 'rating': rating, 'comment': comment}, format='json')

    def _profile(self):
        return ArtistProfile.objects.get(artist_id=self.profile.artist_id)

    def test_cannot_review_a_service_that_has_not_happened(self):
        self.assertEqual(self._rate(self.pending, 5).status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_out_of_range_or_garbage_ratings_are_refused_and_never_counted(self):
        for rating in (0, 6, -1, 10 ** 9, 'abc', None, 4.5, [5], True):
            self.assertEqual(self._rate(self.done, rating).status_code, 400, repr(rating))
        self.assertEqual(Review.objects.count(), 0)
        self.assertEqual(self._profile().total_reviews, 0)

    def test_a_booking_can_only_move_the_rating_once(self):
        self.assertEqual(self._rate(self.done, 5).status_code, 201)
        for _ in range(3):
            self.assertEqual(self._rate(self.done, 1).status_code, 400)
        profile = self._profile()
        self.assertEqual((profile.total_reviews, profile.avg_rating), (1, Decimal('5.00')))

    def test_oversized_comment_is_refused(self):
        self.assertEqual(self._rate(self.done, 5, 'x' * 1001).status_code, 400)
        self.assertEqual(self._rate(self.done, 5, 'x' * 1000).status_code, 201)

    def test_only_the_reviewed_artist_can_reply_and_only_within_the_limit(self):
        self._rate(self.done, 4, 'ok')
        review = Review.objects.get()
        rival_client, _, _ = make_artist(phone_number='+919100000903')
        reply = lambda client, text: client.put('/artists/reviews/reply/', {'review_id': review.review_id, 'reply': text}, format='json')
        self.assertEqual(reply(rival_client, 'I am the real artist').status_code, 400)
        self.assertEqual(reply(self.customer_client, 'self reply').status_code, 400)
        self.assertEqual(reply(self.artist_client, 'x' * 1001).status_code, 400)
        review.refresh_from_db()
        self.assertFalse(review.reply)
        self.assertEqual(reply(self.artist_client, 'Thank you!').status_code, 200)

    def test_artist_cannot_rate_a_customer_for_a_service_that_did_not_happen(self):
        resp = self.artist_client.post('/artists/customer_reviews/create/', {'booking_id': self.pending.booking_id, 'rating': 1}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── 10. Hostile query strings and bodies ─────────────────────────────────────

class HostileInputTest(TestCase):
    SECRET_OTP = 987654

    def setUp(self):
        self.client, self.user = make_customer(phone_number='+919100001001')
        self.other_client, self.other = make_customer(phone_number='+919100001002')
        from sunndari_apps.authentication.models import User
        User.objects.filter(pk=self.other.pk).update(otp=self.SECRET_OTP, refresh_token='refresh-secret-xyz')
        self.other.refresh_from_db()
        # Real rows, so a sort or filter that is wrongly honoured actually changes the output.
        _, _, profile = make_artist(phone_number='+919100001003')
        location = make_location_type()
        sub = make_sub_category()
        for day, price in ((2, 3000), (3, 1000), (4, 2000)):
            package = make_package(profile, sub_category=sub, price=price, name=f'Pkg {price}')
            make_booking(self.user, profile, package, location, booking_date=next_weekday(day),
                         start_time='10:00:00', end_time='11:00:00')
        self.first_booking_id = Booking.objects.filter(customer_id=self.user.user_id).order_by('booking_id').first().booking_id
        self.listings = ['/customers/bookings/get_all/', '/customers/artists/search/', '/customers/reviews/get_all/',
                         '/customers/wallet/transactions/', '/users/address/get_all/', '/customers/bookings/reschedule/get_all/']

    def test_pagination_extremes_never_crash(self):
        for url in self.listings:
            for params in ({'limit': 0}, {'limit': -1}, {'limit': 'abc'}, {'limit': 10 ** 12}, {'page_num': 0},
                           {'page_num': -5}, {'page_num': 'x'}, {'page_num': 10 ** 9}, {'limit': 1, 'page_num': 2 ** 63}):
                resp = self.client.get(url, params)
                self.assertLess(resp.status_code, 500, (url, params))

    def test_sorting_and_filtering_by_secret_columns_is_ignored(self):
        for url in self.listings:
            baseline = self.client.get(url)
            for params in (
                {'sort_by': 'customer__password'}, {'sort_by': 'customer__access_token'}, {'sort_by': '?'},
                {'sort_by': 'booking_id', 'sort_order': 'asc'}, {'sort_by': 'booking_id', 'sort_order': 'desc'},
                {'sort_by': 'total_amount', 'sort_order': 'asc'}, {'sort_by': 'total_amount', 'sort_order': 'desc'},
                {'filter_key': 'booking_id', 'filter_value': str(self.first_booking_id)},
                {'filter_key': 'total_amount', 'filter_value': '1000'},
                {'sort_by': 'booking__customer__otp', 'sort_order': 'desc'},
                {'filter_key': 'customer__otp', 'filter_value': str(self.SECRET_OTP)},
                {'filter_key': 'customer__refresh_token', 'filter_value': 'refresh-secret-xyz'},
                {'filter_key': 'customer__access_token__startswith', 'filter_value': 'eyJ'},
            ):
                resp = self.client.get(url, params)
                self.assertLess(resp.status_code, 500, (url, params))
                if resp.status_code == 400:
                    continue                                                        # rejected outright is fine
                self.assertEqual(resp.status_code, baseline.status_code, (url, params))
                self.assertEqual(resp.content, baseline.content, (url, params))     # else ignored, so no oracle

    def test_injection_strings_in_search_are_just_text(self):
        for text in ("' OR 1=1 --", "'; DROP TABLE users;--", '<script>alert(1)</script>', '%', '_', '\\', '\x00', '🙂' * 200):
            for params in ({'search_key': text}, {'city': text}):
                resp = self.client.get('/customers/artists/search/', params)
                self.assertLess(resp.status_code, 500, repr(text))
                if resp.status_code == 200:
                    self.assertEqual(resp.data['data']['data'], [])

    def test_non_object_json_bodies_are_a_400_not_a_crash(self):
        posts = ['/customers/bookings/create/', '/customers/reviews/create/', '/customers/payments/initiate/',
                 '/help_center/messages/create/', '/auth/phone-otp/request/', '/auth/register/', '/auth/login/']
        for url in posts:
            for body in ([], [1, 2], 'text', 42, None, True):
                resp = self.client.post(url, body, format='json')
                self.assertLess(resp.status_code, 500, (url, body))

    def test_asking_for_secret_columns_by_name_returns_no_secrets(self):
        for values in ('access_token', 'refresh_token', 'otp', 'password', 'accessToken,otp', 'fcm_token', '*'):
            resp = self.client.get('/users/profile/get/', {'user_id': self.other.user_id, 'values': values})
            self.assertLess(resp.status_code, 500, values)
            text = resp.content.decode()
            self.assertNotIn(str(self.SECRET_OTP), text)
            self.assertNotIn('refresh-secret-xyz', text)

    def test_other_peoples_secrets_never_appear_in_any_response(self):
        urls = self.listings + [f'/users/profile/get/?user_id={self.other.user_id}', '/customers/wallet/get/',
                                '/help_center/conversation/get/', '/notifications/get_all/']
        for url in urls:
            text = self.client.get(url).content.decode()
            for secret in (str(self.SECRET_OTP), 'refresh-secret-xyz', self.other.access_token or 'no-token'):
                self.assertNotIn(secret, text, url)

    def test_a_query_string_cannot_override_who_you_are(self):
        # params are merged into the request data, so make sure identity still comes from the token
        resp = self.client.get('/users/address/get_all/', {'user_id': self.other.user_id})
        self.assertLess(resp.status_code, 500)
        self.other_client.post('/users/address/create/', {'address_line_1': 'Secret Lane 9', 'city': 'Delhi', 'pin_code': '110001'}, format='json')
        again = self.client.get('/users/address/get_all/', {'user_id': self.other.user_id, 'user': self.other.user_id})
        self.assertNotIn('Secret Lane 9', again.content.decode())


class PaginationLimitsTest(TestCase):
    """A client chooses the page size, so it must be bounded: one request may not ask the server to build
    millions of rows, and nonsense page numbers are a clean 400."""

    def setUp(self):
        self.client, self.user = make_customer(phone_number='+919100001101')

    def test_page_size_and_page_number_are_bounded(self):
        for url in ('/customers/bookings/get_all/', '/customers/artists/search/', '/users/address/get_all/'):
            for params in ({'limit': 0}, {'limit': -1}, {'limit': 201}, {'limit': 10 ** 12}, {'page_num': 0}, {'page_num': -3}):
                self.assertEqual(self.client.get(url, params).status_code, 400, (url, params))

    def test_the_largest_allowed_page_and_the_defaults_still_work(self):
        for url in ('/customers/bookings/get_all/', '/customers/artists/search/', '/users/address/get_all/'):
            self.assertEqual(self.client.get(url, {'limit': 200, 'page_num': 1}).status_code, 200, url)
            self.assertEqual(self.client.get(url).status_code, 200, url)
