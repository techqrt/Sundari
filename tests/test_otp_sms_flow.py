"""End-to-end phone OTP journey with the SMS gateway (transport mocked: MOCKED, not live)."""
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.authentication.models import User

PHONE = '9624843995'


class OtpSmsJourneyTest(TestCase):
    def setUp(self):
        self.sms = []
        cfg = {'sms_gateway_url': 'http://gw.invalid/api/mt/SendSMS', 'sms_gateway_user': 'u',
               'sms_gateway_password': 'p', 'sms_gateway_sender_id': 'S', 'sms_gateway_route': '29'}
        for key, value in cfg.items():
            patcher = patch.object(Configurations, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        def send(adapter, request, **kwargs):
            self.sms.append({k: v[0] for k, v in parse_qs(urlsplit(request.url).query).items()})
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps({'ErrorCode': '000', 'ErrorMessage': 'Done'}).encode()
            response.url = request.url
            return response
        patcher = patch('requests.adapters.HTTPAdapter.send', send)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient()

    def request_otp(self, phone=PHONE, **extra):
        return self.client.post('/auth/phone-otp/request/', {'phone_number': phone, **extra}, format='json')

    def verify(self, otp, phone=PHONE):
        return self.client.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(otp)}, format='json')

    def test_register_verify_set_password_login_refresh(self):
        # 1. a new artist registers by phone: account + artist profile are created, one SMS goes out
        resp = self.request_otp(role='artist')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.sms), 1)
        user = User.objects.get(phone_number=PHONE)
        self.assertEqual(user.role, 'artist')
        self.assertTrue(ArtistProfile.objects.filter(user_id=user.user_id).exists())
        self.assertIn(f'CODE hai: {user.otp} ', self.sms[0]['text'])
        self.assertEqual(self.sms[0]['number'], PHONE)

        # 2. the OTP from the SMS logs them in and is single-use
        verified = self.verify(user.otp)
        self.assertEqual(verified.status_code, 200)
        data = verified.json()['data']
        self.assertEqual(data['role'], 'artist')
        user.refresh_from_db()
        self.assertIsNone(user.otp)
        self.assertEqual(self.verify(self.sms[0]['text'].split('CODE hai: ')[1][:6]).status_code, 400)

        # 3. the token works; the account has no password yet, so password login is refused
        authed = APIClient()
        authed.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access_token']}")
        profile = authed.get(f"/users/profile/get/?user_id={user.user_id}")
        self.assertEqual(profile.status_code, 200, profile.content)
        no_password = self.client.post('/auth/login/', {'username': PHONE, 'password': 'Whatever@123'}, format='json')
        self.assertEqual(no_password.status_code, 401)

        # 4. set a password (new endpoint), then log in with it and refresh the session
        weak = authed.post('/auth/password/set/', {'new_password': '12345678', 'confirm_password': '12345678'}, format='json')
        self.assertEqual(weak.status_code, 400)
        mismatch = authed.post('/auth/password/set/', {'new_password': 'Sundari@2026', 'confirm_password': 'Sundari@2027'}, format='json')
        self.assertEqual(mismatch.status_code, 400)
        ok = authed.post('/auth/password/set/', {'new_password': 'Sundari@2026', 'confirm_password': 'Sundari@2026'}, format='json')
        self.assertEqual(ok.status_code, 200)
        login = self.client.post('/auth/login/', {'username': PHONE, 'password': 'Sundari@2026'}, format='json')
        self.assertEqual(login.status_code, 200)
        refreshed = self.client.post('/auth/token/refresh/', {'refresh_token': login.json()['data']['refresh_token']}, format='json')
        self.assertEqual(refreshed.status_code, 200)

    def test_returning_user_login_needs_no_role(self):
        User.objects.create(phone_number=PHONE, role='customer', name='Existing')
        self.assertEqual(self.request_otp().status_code, 200)
        self.assertEqual(len(self.sms), 1)
        self.assertEqual(self.verify(User.objects.get(phone_number=PHONE).otp).status_code, 200)

    def test_unknown_number_without_role_sends_nothing(self):
        self.assertEqual(self.request_otp().status_code, 404)
        self.assertEqual(self.sms, [])
        self.assertFalse(User.objects.filter(phone_number=PHONE).exists())

    def test_request_validation_sends_nothing(self):
        bad = [{}, {'phone_number': ''}, {'phone_number': '   ', 'role': 'customer'},
               {'phone_number': '9' * 21, 'role': 'customer'},
               {'phone_number': PHONE, 'role': 'admin'}, {'phone_number': PHONE, 'role': 'nobody'}]
        for body in bad:
            self.assertEqual(self.client.post('/auth/phone-otp/request/', body, format='json').status_code, 400, body)
        self.assertEqual(self.sms, [])
        self.assertFalse(User.objects.exists())

    def test_verify_validation(self):
        self.request_otp(role='customer')
        for otp in ('12345', '1234567', 'abcdef', '', '12 456'):
            self.assertEqual(self.verify(otp).status_code, 400, otp)

    def test_five_wrong_codes_lock_the_account_even_for_the_right_code(self):
        self.request_otp(role='customer')
        for _ in range(5):
            self.assertEqual(self.verify('000000').status_code, 400)
        otp = User.objects.get(phone_number=PHONE).otp
        self.assertEqual(self.verify(otp).status_code, 403)
        self.assertEqual(self.request_otp().status_code, 403)
        self.assertEqual(len(self.sms), 1)                  # no SMS for a locked account

    def test_inactive_account_gets_no_sms_and_cannot_obtain_a_token(self):
        user = User.objects.create(phone_number=PHONE, role='customer', is_active=False, otp=123456,
                                   otp_expiry=timezone.now() + timezone.timedelta(minutes=5))
        resp = self.request_otp()
        self.assertEqual(resp.status_code, 200)                # same answer as for a normal account
        self.assertEqual(self.sms, [])                         # but nothing was sent
        user.refresh_from_db()
        self.assertEqual(user.otp, 123456)                     # and no new code was generated
        self.assertEqual(self.verify(123456).status_code, 403)

    def test_resend_inside_the_cooldown_is_refused_without_an_sms(self):
        self.assertEqual(self.request_otp(role='customer').status_code, 200)
        first = User.objects.get(phone_number=PHONE).otp
        again = self.request_otp()
        self.assertEqual(again.status_code, 400)
        self.assertFalse(again.json()['status'])
        self.assertEqual(len(self.sms), 1)
        self.assertEqual(User.objects.get(phone_number=PHONE).otp, first)   # code unchanged
        # once the cooldown has passed a new code goes out
        past = timezone.now() - timezone.timedelta(seconds=Configurations.otp_resend_seconds + 5)
        User.objects.filter(phone_number=PHONE).update(
            otp_expiry=past + timezone.timedelta(minutes=Configurations.otp_expiry_minutes))
        self.assertEqual(self.request_otp().status_code, 200)
        self.assertEqual(len(self.sms), 2)

    def test_successful_login_clears_the_cooldown(self):
        self.request_otp(role='customer')
        self.assertEqual(self.verify(User.objects.get(phone_number=PHONE).otp).status_code, 200)
        self.assertEqual(self.request_otp().status_code, 200)

    def test_resend_does_not_reset_the_wrong_guess_counter(self):
        self.request_otp(role='customer')
        for _ in range(4):
            self.verify('000000')
        long_ago = timezone.now() - timezone.timedelta(seconds=Configurations.otp_resend_seconds + 5)
        User.objects.filter(phone_number=PHONE).update(      # pretend the last request was past the cooldown
            otp_expiry=long_ago + timezone.timedelta(minutes=Configurations.otp_expiry_minutes))
        self.assertEqual(self.request_otp().status_code, 200)             # a fresh code is issued…
        self.assertEqual(User.objects.get(phone_number=PHONE).otp_attempts, 4)   # …the budget is not
        self.assertEqual(self.verify('000000').status_code, 400)
        self.assertEqual(self.verify('000000').status_code, 403)          # locked on the 5th wrong guess in total

    def test_phone_validation_rejects_junk_and_sends_nothing(self):
        for junk in ('abc', '0', '12345', '9' * 11, '5123456789', '+1 415 555 2671', '98765-4321x', '+91 12345 67890'):
            resp = self.client.post('/auth/phone-otp/request/', {'phone_number': junk, 'role': 'customer'}, format='json')
            self.assertEqual(resp.status_code, 400, junk)
        self.assertEqual(self.sms, [])
        self.assertFalse(User.objects.exists())

    def test_formatting_variants_resolve_to_one_account(self):
        self.assertEqual(self.request_otp('+91 96248 43995', role='customer').status_code, 200)
        self.assertEqual(User.objects.get().phone_number, '+919624843995')        # stored without separators, as sent
        for variant in ('9624843995', '09624843995', '919624843995', '+919624843995', '96248-43995'):
            User.objects.update(otp_expiry=None)                                   # skip the cooldown
            self.assertEqual(self.request_otp(variant, role='customer').status_code, 200, variant)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual({sms['number'] for sms in self.sms}, {PHONE})            # one handset, one national number
        otp = User.objects.get().otp
        self.assertEqual(self.verify(otp, phone='9624843995').status_code, 200)   # verify accepts any variant

    def test_gateway_outage_blocks_login_cleanly_and_recovers(self):
        def down(adapter, request, **kwargs):
            raise requests.ConnectTimeout('timed out')
        with patch('requests.adapters.HTTPAdapter.send', down), \
                self.assertLogs('sunndari_apps.authentication.utils', level='WARNING'):
            resp = self.request_otp(role='customer')
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(resp.json()['status'])
        # gateway back: the same request now succeeds and the code that was SMSed verifies
        self.assertEqual(self.request_otp(role='customer').status_code, 200)
        self.assertEqual(self.verify(User.objects.get(phone_number=PHONE).otp).status_code, 200)


class OtherFlowsUnchangedTest(OtpSmsJourneyTest):
    """The gateway is for phone login/register only; these flows keep their previous behaviour."""

    def test_forgot_password_by_phone_does_not_use_the_gateway_flag(self):
        User.objects.create(phone_number='+919876500001', role='customer', name='x')
        with patch('sunndari_apps.authentication.views.send_otp_sms') as sms:
            self.client.post('/auth/forgot-password/', {'username': '+919876500001'}, format='json')
        sms.assert_called_once()
        self.assertFalse(sms.call_args.kwargs.get('via_gateway', False))
        self.assertEqual(self.sms, [])

    def test_contact_change_by_phone_does_not_use_the_gateway_flag(self):
        user = User.objects.create(phone_number='+919876500002', role='customer', name='x', email='a@b.in')
        from sunndari_apps.authentication.utils import generate_jwt_token
        token = generate_jwt_token(user)
        user.access_token = token
        user.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        with patch('sunndari_apps.users.views.contact_change.send_otp_sms') as sms:
            resp = client.post('/users/contact/change/request/', {'phone_number': '+919876500003'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(sms.call_args.kwargs.get('via_gateway', False))
        self.assertEqual(self.sms, [])

    def test_email_otp_still_works_and_shares_the_kept_counter(self):
        User.objects.create(email='who@example.com', role='customer', name='x')
        with patch('sunndari_apps.authentication.views.send_otp_email'):
            self.assertEqual(self.client.post('/auth/email-otp/request/', {'email': 'who@example.com'}, format='json').status_code, 200)
        for _ in range(2):
            self.client.post('/auth/email-otp/verify/', {'email': 'who@example.com', 'otp': '000000'}, format='json')
        with patch('sunndari_apps.authentication.views.send_otp_email'):
            self.client.post('/auth/email-otp/request/', {'email': 'who@example.com'}, format='json')
        user = User.objects.get(email='who@example.com')
        self.assertEqual(user.otp_attempts, 2)            # a resend does not hand back the budget
        ok = self.client.post('/auth/email-otp/verify/', {'email': 'who@example.com', 'otp': str(user.otp)}, format='json')
        self.assertEqual(ok.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.otp_attempts, 0)            # success resets it, as before

    def test_legacy_account_with_an_odd_number_can_still_log_in_by_otp(self):
        User.objects.create(phone_number='+99999999999', role='customer', name='legacy')   # not a valid mobile
        self.assertEqual(self.request_otp('+99999999999').status_code, 200)
        self.assertEqual(self.verify(User.objects.get(phone_number='+99999999999').otp, phone='+99999999999').status_code, 200)
        # …but such a number cannot be used to CREATE a new account
        resp = self.client.post('/auth/phone-otp/request/', {'phone_number': '+99999999998', 'role': 'customer'}, format='json')
        self.assertEqual(resp.status_code, 400)
