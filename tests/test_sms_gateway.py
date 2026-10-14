"""SMS gateway integration for the phone login/register OTP.

The HTTP boundary (requests' transport adapter) is mocked, so real request preparation and URL
encoding are exercised but nothing ever leaves the machine. These are MOCKED tests: they do not
prove the live provider accepts the request."""
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import SMSDeliveryError, send_otp_sms

SECRET = 'S3cr3t-gw-pass'
GATEWAY = {
    'sms_gateway_url': 'http://gateway.invalid/api/mt/SendSMS',
    'sms_gateway_user': 'acct-user',
    'sms_gateway_password': SECRET,
    'sms_gateway_sender_id': 'SNDR01',
    'sms_gateway_route': '29',
}
OK_BODY = json.dumps({'ErrorCode': '000', 'ErrorMessage': 'Done', 'JobId': '1'})


def reply(request, status=200, body=OK_BODY, content_type='application/json'):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    response.headers['Content-Type'] = content_type
    response.url = request.url
    response.request = request
    return response


class GatewayCase(TestCase):
    url = '/auth/phone-otp/request/'
    phone = '+919812345670'

    def setUp(self):
        self.sent = []
        patchers = [patch.object(Configurations, k, v) for k, v in GATEWAY.items()]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.client = APIClient()

    def transport(self, handler=None):
        def send(adapter, request, **kwargs):
            self.sent.append((request, kwargs))
            return handler(request) if handler else reply(request)
        return patch('requests.adapters.HTTPAdapter.send', send)

    def post(self, **extra):
        return self.client.post(self.url, {'phone_number': self.phone, 'role': 'customer', **extra}, format='json')

    @staticmethod
    def query(request):
        return {k: v[0] for k, v in parse_qs(urlsplit(request.url).query).items()}


class A_SuccessfulSubmissionTest(GatewayCase):
    def test_otp_endpoint_submits_the_generated_code_with_the_documented_parameters(self):
        with self.transport():
            resp = self.post()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['status'])
        self.assertEqual(resp.json()['message'], 'OTP sent successfully')
        self.assertEqual(len(self.sent), 1)
        request, kwargs = self.sent[0]
        q = self.query(request)
        otp = User.objects.get(phone_number=self.phone).otp
        self.assertEqual(request.method, 'GET')
        self.assertEqual(urlsplit(request.url).path, '/api/mt/SendSMS')
        self.assertEqual({k: q[k] for k in ('user', 'senderid', 'channel', 'DCS', 'flashsms', 'route')},
                         {'user': 'acct-user', 'senderid': 'SNDR01', 'channel': 'Trans', 'DCS': '0',
                          'flashsms': '0', 'route': '29'})
        self.assertEqual(q['password'], SECRET)
        self.assertEqual(q['number'], '9812345670')            # national 10-digit form, like the gateway sample
        self.assertIn(f'SUNNDARI CODE hai: {otp} Ye agle 10 minutes tak valid hai.', q['text'])
        self.assertEqual(kwargs['timeout'], (3, 10))

    def test_message_is_url_encoded_not_concatenated(self):
        with self.transport():
            self.post()
        raw = self.sent[0][0].url
        self.assertNotIn(' ', raw)                                  # spaces are escaped
        text_part = raw.split('text=')[1].split('&')[0]
        self.assertTrue(text_part.startswith('Sunndari%20par') or text_part.startswith('Sunndari+par'))
        self.assertIn('%21', text_part)                             # '!' is escaped too

    def test_sms_uses_the_otp_that_verify_accepts(self):
        with self.transport():
            self.post()
        otp = User.objects.get(phone_number=self.phone).otp
        self.assertIn(str(otp), self.query(self.sent[0][0])['text'])
        resp = self.client.post('/auth/phone-otp/verify/', {'phone_number': self.phone, 'otp': str(otp)}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_expiry_text_matches_the_real_expiry(self):
        with self.transport():
            self.post()
        user = User.objects.get(phone_number=self.phone)
        minutes = round((user.otp_expiry - timezone.now()).total_seconds() / 60)
        self.assertEqual(minutes, Configurations.otp_expiry_minutes)
        self.assertIn(f'agle {minutes} minutes', self.query(self.sent[0][0])['text'])


class B_GatewayFailureTest(GatewayCase):
    def assert_safe_failure(self, resp, logs):
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertFalse(body['status'])
        self.assertEqual(body['message'], 'Unable to send OTP right now, please try again')
        otp = str(User.objects.get(phone_number=self.phone).otp)
        blob = json.dumps(body) + '\n'.join(logs.output)
        for secret in (SECRET, otp, 'acct-user', 'gateway.invalid'):
            self.assertNotIn(secret, blob)

    def run_failing(self, handler):
        with self.transport(handler), self.assertLogs('sunndari_apps.authentication.utils', level='WARNING') as logs:
            resp = self.post()
        self.assert_safe_failure(resp, logs)

    def test_connection_error_whose_message_contains_the_url(self):
        def boom(request):
            raise requests.ConnectionError(f'Max retries exceeded with url: {request.url}')
        self.run_failing(boom)

    def test_connect_timeout(self):
        def boom(request):
            raise requests.ConnectTimeout('connect timed out')
        self.run_failing(boom)

    def test_read_timeout(self):
        def boom(request):
            raise requests.ReadTimeout('read timed out')
        self.run_failing(boom)

    def test_http_error_status(self):
        self.run_failing(lambda r: reply(r, status=500, body='error'))

    def test_malformed_provider_response(self):
        self.run_failing(lambda r: reply(r, body='<html>oops</html>', content_type='text/html'))

    def test_json_without_error_code(self):
        self.run_failing(lambda r: reply(r, body='{"hello": 1}'))

    def test_provider_rejection_despite_http_200(self):
        self.run_failing(lambda r: reply(r, body=json.dumps({'ErrorCode': '006', 'ErrorMessage': 'Invalid Password'})))

    def test_missing_configuration_makes_no_request(self):
        with patch.object(Configurations, 'sms_gateway_password', ''), self.transport(), \
                self.assertLogs('sunndari_apps.authentication.utils', level='ERROR') as logs:
            resp = self.post()
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(self.sent, [])
        self.assertNotIn(SECRET, '\n'.join(logs.output))

    def test_failed_send_drops_the_code_and_allows_an_immediate_retry(self):
        def boom(request):
            raise requests.ConnectTimeout('x')
        with self.transport(boom), self.assertLogs('sunndari_apps.authentication.utils', level='WARNING'):
            self.assertEqual(self.post().status_code, 503)
        user = User.objects.get(phone_number=self.phone)
        self.assertIsNone(user.otp)
        self.assertIsNone(user.otp_expiry)
        with self.transport():
            self.assertEqual(self.post().status_code, 200)        # no cooldown after a failed send
        self.assertIsNotNone(User.objects.get(phone_number=self.phone).otp)


class C_RegressionTest(GatewayCase):
    def test_invalid_otp_still_rejected(self):
        with self.transport():
            self.post()
        otp = User.objects.get(phone_number=self.phone).otp
        wrong = str(100000 + (otp - 100000 + 1) % 900000)
        resp = self.client.post('/auth/phone-otp/verify/', {'phone_number': self.phone, 'otp': wrong}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_expired_otp_still_rejected(self):
        with self.transport():
            self.post()
        user = User.objects.get(phone_number=self.phone)
        User.objects.filter(pk=user.pk).update(otp_expiry=timezone.now() - timezone.timedelta(minutes=1))
        resp = self.client.post('/auth/phone-otp/verify/', {'phone_number': self.phone, 'otp': str(user.otp)}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_used_otp_cannot_be_reused(self):
        with self.transport():
            self.post()
        otp = User.objects.get(phone_number=self.phone).otp
        payload = {'phone_number': self.phone, 'otp': str(otp)}
        self.assertEqual(self.client.post('/auth/phone-otp/verify/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/auth/phone-otp/verify/', payload, format='json').status_code, 400)

    def test_resend_replaces_the_code_and_sends_again(self):
        with self.transport():
            self.post()
            first = User.objects.get(phone_number=self.phone).otp
            User.objects.filter(phone_number=self.phone).update(otp_expiry=timezone.now() + timezone.timedelta(minutes=5))
            self.assertEqual(self.post().status_code, 200)         # past the resend cooldown
        self.assertEqual(len(self.sent), 2)
        self.assertIn(str(User.objects.get(phone_number=self.phone).otp), self.query(self.sent[1][0])['text'])
        self.assertIsNotNone(first)

    def test_other_otp_flows_do_not_use_the_gateway(self):
        User.objects.create(phone_number='+919812345671', role='customer', name='x')
        with self.transport():
            resp = self.client.post('/auth/forgot-password/', {'username': '+919812345671'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.sent, [])
        with self.transport():
            send_otp_sms('+919812345671', 123456)          # default (booking OTP, contact change, …)
        self.assertEqual(self.sent, [])

    @override_settings(DEBUG=True)
    def test_debug_without_gateway_config_still_prints_and_succeeds(self):
        with patch.object(Configurations, 'sms_gateway_url', ''), self.transport():
            resp = self.post()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.sent, [])

    @override_settings(DEBUG=False)
    def test_unconfigured_gateway_outside_debug_raises_not_false_success(self):
        with patch.object(Configurations, 'sms_gateway_url', ''), self.assertLogs('sunndari_apps.authentication.utils', level='ERROR'):
            with self.assertRaises(SMSDeliveryError):
                send_otp_sms(self.phone, 123456, via_gateway=True)


class D_DebugModeMatrixTest(GatewayCase):
    """DEBUG x gateway-configured x via_gateway: what actually happens to the code."""

    def run_case(self, debug, configured, via_gateway):
        import contextlib
        import io
        printed = io.StringIO()
        raised = False
        url = GATEWAY['sms_gateway_url'] if configured else ''
        with override_settings(DEBUG=debug), patch.object(Configurations, 'sms_gateway_url', url), \
                self.transport(), contextlib.redirect_stdout(printed):
            try:
                send_otp_sms('9624843995', 482913, via_gateway=via_gateway)
            except SMSDeliveryError:
                raised = True
        return {'gateway_calls': len(self.sent), 'printed_otp': '482913' in printed.getvalue(), 'raised': raised}

    def test_matrix(self):
        expected = {
            # (debug, configured, via_gateway): (gateway_calls, printed_otp, raised)
            (True, True, True): (1, False, False),
            (True, False, True): (0, True, False),       # developer without a provider sees the code
            (False, True, True): (1, False, False),
            (False, False, True): (0, False, True),      # production misconfiguration is loud, not a false success
            (True, True, False): (0, True, False),       # every other flow: unchanged
            (True, False, False): (0, True, False),
            (False, True, False): (0, False, False),
            (False, False, False): (0, False, False),
        }
        for (debug, configured, via), want in expected.items():
            self.sent.clear()
            got = self.run_case(debug, configured, via)
            self.assertEqual((got['gateway_calls'], got['printed_otp'], got['raised']), want,
                             f'debug={debug} configured={configured} via_gateway={via}')

    def test_no_otp_or_secret_in_logs_when_configured_and_not_debug(self):
        with override_settings(DEBUG=False), self.transport(), \
                self.assertLogs('sunndari_apps.authentication.utils', level='DEBUG') as logs:
            send_otp_sms('9624843995', 482913, via_gateway=True)
            logging_probe = __import__('logging').getLogger('sunndari_apps.authentication.utils')
            logging_probe.info('probe')                     # assertLogs needs at least one record
        blob = '\n'.join(logs.output)
        for secret in ('482913', SECRET, 'gateway.invalid', '9624843995'):
            self.assertNotIn(secret, blob)
