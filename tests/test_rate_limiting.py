"""Rate limits: the SMS-bombing / password-guessing / scraping ceiling. The test runner's own limits are set so high
that no other test can reach them; these tests lower them for one case at a time."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tests.test_customers import make_customer


class AuthThrottleTest(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(AUTH_THROTTLE_RATE='3/min')
    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_otp_requests_are_capped_per_client_across_different_phone_numbers(self, sms):
        client = APIClient()
        codes = [client.post('/auth/phone-otp/request/', {'phone_number': f'+91980000{n:04d}', 'role': 'customer'}).status_code
                 for n in range(6)]
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3:], [429, 429, 429])
        self.assertEqual(sms.call_count, 3)                                   # the SMS bill stops at the limit

    @override_settings(AUTH_THROTTLE_RATE='3/min')
    def test_password_guessing_is_capped(self):
        client = APIClient()
        codes = [client.post('/auth/login/', {'username': '+919800001111', 'password': f'guess{n}'}, format='json').status_code
                 for n in range(6)]
        self.assertEqual(codes[3:], [429, 429, 429])

    @override_settings(AUTH_THROTTLE_RATE='3/min')
    def test_a_throttled_response_says_when_to_retry(self):
        client = APIClient()
        for _ in range(3):
            client.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json')
        blocked = client.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json')
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked['Retry-After']), 0)

    @override_settings(AUTH_THROTTLE_RATE='3/min')
    def test_a_forged_forwarded_for_header_does_not_buy_more_attempts(self):
        client = APIClient()
        codes = [client.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json',
                             HTTP_X_FORWARDED_FOR=f'10.0.0.{n}').status_code for n in range(6)]
        self.assertEqual(codes[3:], [429, 429, 429])

    @override_settings(AUTH_THROTTLE_RATE='3/min')
    def test_different_clients_have_separate_allowances(self):
        first, second = APIClient(), APIClient()
        for _ in range(4):
            first.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json', REMOTE_ADDR='203.0.113.1')
        self.assertEqual(first.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json', REMOTE_ADDR='203.0.113.1').status_code, 429)
        self.assertNotEqual(second.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json', REMOTE_ADDR='203.0.113.2').status_code, 429)

    def test_normal_use_is_not_affected_at_the_shipped_default(self):
        client = APIClient()
        with override_settings(AUTH_THROTTLE_RATE='30/min'):
            codes = {client.post('/auth/login/', {'username': 'a', 'password': 'b'}, format='json').status_code for _ in range(10)}
        self.assertNotIn(429, codes)


class UserThrottleTest(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(USER_THROTTLE_RATE='5/min')
    def test_a_signed_in_user_is_capped_but_other_users_are_not(self):
        busy, _ = make_customer(phone_number='+919300002001')
        calm, _ = make_customer(phone_number='+919300002002')
        codes = [busy.get('/users/address/get_all/').status_code for _ in range(8)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5:], [429, 429, 429])
        self.assertEqual(calm.get('/users/address/get_all/').status_code, 200)       # same IP, different user

    @override_settings(USER_THROTTLE_RATE='5/min')
    def test_the_gateway_webhook_is_never_throttled(self):
        client = APIClient()
        codes = {client.generic('POST', '/customers/payments/webhook/razorpay/', b'{}', content_type='application/json').status_code
                 for _ in range(10)}
        self.assertNotIn(429, codes)
