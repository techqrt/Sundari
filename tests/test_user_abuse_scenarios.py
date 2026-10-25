"""Ways real users (careless or hostile) push on the system, each pinned by a test that asserts the
SAFE outcome — a failure here is a real hole, not a test quirk.

1. Two people grab the same slot (or one person double-taps "Book").
2. Double-tapping "Pay" / replaying the payment confirmation.
3. Guessing or flooding sign-in OTPs.
4. Reaching for another customer's booking, PIN, payment and support chat by id.
5. Using a session that should be dead (deactivated account, replaced login, wrong token type).
"""
import jwt
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token, generate_refresh_token
from sunndari_apps.customers.models import Booking
from sunndari_apps.help_center.models import SupportConversation
from sunndari_apps.payments.models import Payment

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type, make_package,
    make_location_preference, make_schedule, seed_booking_statuses, seed_payment_statuses, next_weekday,
)

BOOK = '/customers/bookings/create/'


class MarketplaceMixin:
    """One approved artist with a 60-minute, 1500 package open on a future weekday."""

    def setUp(self):
        super().setUp()
        seed_booking_statuses()
        seed_payment_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919100000001')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=60)
        self.location = make_location_type()
        make_location_preference(self.profile, self.location)
        self.day = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.day.weekday())

    def book(self, client, start='10:00:00'):
        return client.post(BOOK, {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.day.strftime('%d-%m-%y'), 'start_time': start,
        }, format='json')

    def live_bookings(self):
        return Booking.objects.filter(artist_id=self.profile.artist_id).exclude(status__name='cancelled')


# ─── 1. Two people grab the same slot ─────────────────────────────────────────

class SlotContentionTest(MarketplaceMixin, TestCase):

    def test_second_customer_cannot_take_an_already_booked_slot(self):
        first, _ = make_customer(phone_number='+919100000101')
        second, _ = make_customer(phone_number='+919100000102')
        self.assertEqual(self.book(first).status_code, 201)
        self.assertEqual(self.book(second).status_code, 400)
        self.assertEqual(self.live_bookings().count(), 1)

    def test_double_tap_by_one_customer_creates_one_booking(self):
        client, _ = make_customer(phone_number='+919100000103')
        statuses = [self.book(client).status_code, self.book(client).status_code]
        self.assertEqual(sorted(statuses), [201, 400])
        self.assertEqual(self.live_bookings().count(), 1)

    def test_an_overlapping_start_time_is_refused(self):
        first, _ = make_customer(phone_number='+919100000104')
        second, _ = make_customer(phone_number='+919100000105')
        self.assertEqual(self.book(first, start='10:00:00').status_code, 201)
        self.assertEqual(self.book(second, start='10:30:00').status_code, 400)   # inside 10:00-11:00
        self.assertEqual(self.live_bookings().count(), 1)

    def test_a_cancelled_slot_can_be_booked_again(self):
        first, _ = make_customer(phone_number='+919100000106')
        second, _ = make_customer(phone_number='+919100000107')
        booking_id = self.book(first).data['data']['booking_id']
        self.assertEqual(first.put('/customers/bookings/cancel/', {'booking_id': booking_id}, format='json').status_code, 200)
        self.assertEqual(self.book(second).status_code, 201)


# ─── 2. Double-tapping "Pay" ──────────────────────────────────────────────────

class DoublePaymentTest(MarketplaceMixin, TestCase):

    def setUp(self):
        super().setUp()
        # The same RazorpayGateway singleton serves initiate and verify, so one patch covers both.
        client_mock = MagicMock()
        client_mock.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        client_mock.utility.verify_payment_signature.return_value = None
        patcher = patch(
            'sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client', return_value=client_mock,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.gateway = client_mock
        self.customer_client, self.customer = make_customer(phone_number='+919100000201')
        self.booking_id = self.book(self.customer_client).data['data']['booking_id']

    def _settled_total(self):
        return Payment.objects.filter(booking_id=self.booking_id, status__name='paid').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    def _committed_total(self):
        """Paid plus still-pending orders: what the customer could end up being charged."""
        return Payment.objects.filter(
            booking_id=self.booking_id, status__name__in=['paid', 'pending'],
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    def test_tapping_pay_twice_never_commits_more_than_the_total(self):
        total = Booking.objects.get(booking_id=self.booking_id).total_amount
        for _ in range(3):
            self.customer_client.post('/customers/payments/initiate/', {'booking_id': self.booking_id}, format='json')
        self.assertLessEqual(self._committed_total(), total)

    def test_replaying_the_payment_confirmation_settles_only_once(self):
        resp = self.customer_client.post('/customers/payments/initiate/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 201)
        order_id, paise = resp.data['data']['gateway_order_id'], resp.data['data']['amount']
        self.gateway.payment.fetch.return_value = {'id': 'pay_replay', 'order_id': order_id, 'status': 'captured', 'amount': paise}
        self.gateway.order.fetch.return_value = {
            'id': order_id, 'amount': paise, 'amount_paid': paise, 'amount_due': 0, 'currency': 'INR', 'status': 'paid',
        }
        confirm = {'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_replay', 'razorpay_signature': 'sig'}
        self.customer_client.post('/customers/payments/verify/', confirm, format='json')
        self.customer_client.post('/customers/payments/verify/', confirm, format='json')
        self.assertEqual(self._settled_total(), Booking.objects.get(booking_id=self.booking_id).total_amount)
        self.assertEqual(Payment.objects.filter(booking_id=self.booking_id, status__name='paid').count(), 1)

    def test_a_forged_payment_confirmation_does_not_settle_the_booking(self):
        resp = self.customer_client.post('/customers/payments/initiate/', {'booking_id': self.booking_id}, format='json')
        order_id = resp.data['data']['gateway_order_id']
        self.gateway.utility.verify_payment_signature.side_effect = Exception('bad signature')
        forged = self.customer_client.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_fake', 'razorpay_signature': 'forged',
        }, format='json')
        self.assertGreaterEqual(forged.status_code, 400)
        self.assertEqual(self._settled_total(), Decimal('0'))


# ─── 3. Guessing or flooding sign-in OTPs ─────────────────────────────────────

class OtpAbuseTest(TestCase):
    PHONE = '+919100000301'

    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_requesting_codes_in_a_burst_sends_only_one_sms(self, sms):
        statuses = [
            self.client.post('/auth/phone-otp/request/', {'phone_number': self.PHONE, 'role': 'customer'}).status_code
            for _ in range(5)
        ]
        self.assertEqual(statuses[0], 200)
        self.assertTrue(all(code == 400 for code in statuses[1:]))
        self.assertEqual(sms.call_count, 1)

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_guessing_the_code_locks_the_account_even_for_the_right_code(self, sms):
        self.client.post('/auth/phone-otp/request/', {'phone_number': self.PHONE, 'role': 'customer'})
        user = User.objects.get(phone_number=self.PHONE)
        right = user.otp
        wrong = 111111 if right != 111111 else 222222
        for _ in range(8):
            self.client.post('/auth/phone-otp/verify/', {'phone_number': self.PHONE, 'otp': str(wrong)})
        resp = self.client.post('/auth/phone-otp/verify/', {'phone_number': self.PHONE, 'otp': str(right)})
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertNotIn('access_token', (resp.data.get('data') or {}))

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_a_code_works_once_and_cannot_be_replayed(self, sms):
        self.client.post('/auth/phone-otp/request/', {'phone_number': self.PHONE, 'role': 'customer'})
        code = str(User.objects.get(phone_number=self.PHONE).otp)
        self.assertEqual(self.client.post('/auth/phone-otp/verify/', {'phone_number': self.PHONE, 'otp': code}).status_code, 200)
        self.assertEqual(self.client.post('/auth/phone-otp/verify/', {'phone_number': self.PHONE, 'otp': code}).status_code, 400)

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_registering_a_junk_number_is_refused_so_no_sms_is_ever_attempted(self, sms):
        resp = self.client.post('/auth/phone-otp/request/', {'phone_number': 'abc', 'role': 'customer'})
        self.assertEqual(resp.status_code, 400)
        sms.assert_not_called()
        self.assertFalse(User.objects.filter(phone_number='abc').exists())


# ─── 4. Reaching for someone else's data by id ────────────────────────────────

class CrossCustomerAccessTest(MarketplaceMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.victim_client, self.victim = make_customer(phone_number='+919100000401')
        self.attacker_client, self.attacker = make_customer(phone_number='+919100000402')
        self.booking_id = self.book(self.victim_client).data['data']['booking_id']

    def _victim_booking_status(self):
        return Booking.objects.get(booking_id=self.booking_id).status.name

    def test_cannot_cancel_someone_elses_booking(self):
        resp = self.attacker_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._victim_booking_status(), 'pending')

    def test_cannot_read_someone_elses_booking_or_pins(self):
        for url in ('/customers/bookings/get/', '/customers/bookings/start_pin/', '/customers/bookings/completion_pin/'):
            resp = self.attacker_client.get(url, {'booking_id': self.booking_id})
            self.assertEqual(resp.status_code, 400, url)
        listed = self.attacker_client.get('/customers/bookings/get_all/')
        self.assertNotIn(self.booking_id, [b['bookingId'] for b in listed.data['data']['data']])

    def test_cannot_start_a_payment_for_someone_elses_booking(self):
        before = Payment.objects.count()
        resp = self.attacker_client.post('/customers/payments/initiate/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Payment.objects.count(), before)

    def test_cannot_review_a_booking_that_is_not_theirs(self):
        resp = self.attacker_client.post('/customers/reviews/create/', {'booking_id': self.booking_id, 'rating': 1}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_cannot_read_another_users_support_chat(self):
        self.victim_client.post('/help_center/messages/create/', {'content': 'my private issue', 'subject': 'Refund'}, format='json')
        conversation_id = SupportConversation.objects.get(customer_id=self.victim.user_id).conversation_id
        resp = self.attacker_client.get('/help_center/messages/get_all/', {'conversation_id': conversation_id})
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn('my private issue', str(resp.data))
        own = self.attacker_client.get('/help_center/conversation/get/')
        self.assertIsNone(own.data['data'])

    def test_a_customer_cannot_use_the_admin_support_endpoints(self):
        self.victim_client.post('/help_center/messages/create/', {'content': 'hi'}, format='json')
        conversation_id = SupportConversation.objects.get(customer_id=self.victim.user_id).conversation_id
        for resp in (
            self.attacker_client.get('/help_center/admin/conversations/get_all/'),
            self.attacker_client.post('/help_center/admin/messages/create/', {'conversation_id': conversation_id, 'content': 'x'}, format='json'),
            self.attacker_client.post('/help_center/admin/conversation/close/', {'conversation_id': conversation_id}, format='json'),
        ):
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(SupportConversation.objects.get(conversation_id=conversation_id).status, 'open')


# ─── 5. Using a session that should be dead ───────────────────────────────────

class DeadSessionTest(TestCase):

    def setUp(self):
        self.client_a, self.user = make_customer(phone_number='+919100000501')
        self.old_token = self.user.access_token
        self.profile_url = '/users/address/get_all/'

    def _call(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client.get(self.profile_url)

    def test_a_deactivated_account_is_locked_out_immediately(self):
        self.assertEqual(self._call(self.old_token).status_code, 200)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self._call(self.old_token).status_code, 401)

    def test_signing_in_again_ends_the_old_session(self):
        # A second sign-in in the same second would mint a byte-identical token, so make it distinct.
        payload = jwt.decode(self.old_token, settings.SECRET_KEY, algorithms=['HS256'])
        new_token = jwt.encode({**payload, 'jti': 'second-login'}, settings.SECRET_KEY, algorithm='HS256')
        User.objects.filter(pk=self.user.pk).update(access_token=new_token)
        self.assertEqual(self._call(self.old_token).status_code, 401)
        self.assertEqual(self._call(new_token).status_code, 200)

    def test_a_refresh_token_cannot_be_used_as_an_access_token(self):
        refresh = generate_refresh_token(self.user)
        User.objects.filter(pk=self.user.pk).update(refresh_token=refresh)
        self.assertEqual(self._call(refresh).status_code, 401)

    def test_tampered_and_garbage_tokens_are_rejected(self):
        head, payload, sig = self.old_token.split('.')
        for token in (f'{head}.{payload}.{sig[:-2]}xx', 'not-a-token', '', self.old_token + 'x'):
            self.assertEqual(self._call(token).status_code, 401, token[:20])
