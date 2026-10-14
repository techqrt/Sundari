"""Real HTTP end to end: a live Django server thread, a real HTTP client, and a stand-in SMS
gateway on a local socket. Nothing leaves the machine; the real provider is never contacted.
(Local socket test = real request encoding, timeouts and wire format; not a live-provider test.)"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests
from django.test import LiveServerTestCase

from sunndari.config import Configurations
from sunndari_apps.authentication.models import User

PHONE = '9624843995'


class FakeGateway:
    """mode: ok | reject | error | slow"""
    def __init__(self):
        self.mode = 'ok'
        self.calls = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlsplit(self.path)
                outer.calls.append({k: v[0] for k, v in parse_qs(parts.query).items()} | {'_path': parts.path})
                if outer.mode == 'slow':
                    time.sleep(3)
                if outer.mode == 'error':
                    self.send_response(500); self.end_headers(); self.wfile.write(b'boom'); return
                body = {'ErrorCode': '006' if outer.mode == 'reject' else '000',
                        'ErrorMessage': 'Invalid Password' if outer.mode == 'reject' else 'Done'}
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/api/mt/SendSMS'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class LiveStackOtpTest(LiveServerTestCase):
    def setUp(self):
        self.gateway = FakeGateway()
        self.addCleanup(self.gateway.stop)
        cfg = {'sms_gateway_url': self.gateway.url, 'sms_gateway_user': 'acct', 'sms_gateway_password': 'pw-123',
               'sms_gateway_sender_id': 'SNNDAR', 'sms_gateway_route': '29', 'sms_gateway_read_timeout_seconds': 1}
        for key, value in cfg.items():
            patcher = patch.object(Configurations, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, method, path, token=None, **kwargs):
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        return requests.request(method, self.live_server_url + path, headers=headers, timeout=15, **kwargs)

    def test_full_journey_over_real_http(self):
        r = self.call('POST', '/auth/phone-otp/request/', json={'phone_number': '+91 96248 43995', 'role': 'artist'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.gateway.calls), 1)
        sms = self.gateway.calls[0]
        user = User.objects.get(phone_number='+919624843995')
        self.assertEqual((sms['_path'], sms['number'], sms['senderid'], sms['route'], sms['channel']),
                         ('/api/mt/SendSMS', PHONE, 'SNNDAR', '29', 'Trans'))
        self.assertIn(f'CODE hai: {user.otp} ', sms['text'])
        self.assertIn('10 minutes', sms['text'])

        r = self.call('POST', '/auth/phone-otp/verify/', json={'phone_number': PHONE, 'otp': str(user.otp)})
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()['data']['access_token']

        r = self.call('GET', f'/users/profile/get/?user_id={user.user_id}', token=token)
        self.assertEqual(r.status_code, 200, r.text)                  # blank name must not break it
        r = self.call('POST', '/auth/password/set/', token=token,
                      json={'new_password': 'Sundari@2026', 'confirm_password': 'Sundari@2026'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.call('POST', '/auth/login/', json={'username': '+919624843995', 'password': 'Sundari@2026'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.call('POST', '/auth/token/refresh/', json={'refresh_token': r.json()['data']['refresh_token']})
        self.assertEqual(r.status_code, 200, r.text)

    def test_provider_rejection_and_http_error_surface_as_503(self):
        for mode in ('reject', 'error'):
            self.gateway.mode = mode
            r = self.call('POST', '/auth/phone-otp/request/', json={'phone_number': PHONE, 'role': 'customer'})
            self.assertEqual(r.status_code, 503, mode)
            body = r.text
            for leaked in ('pw-123', 'acct', '127.0.0.1', str(User.objects.get(phone_number=PHONE).otp)):
                self.assertNotIn(leaked, body)
            self.assertIsNone(User.objects.get(phone_number=PHONE).otp)

    def test_slow_gateway_is_cut_off_by_the_read_timeout_then_recovers(self):
        self.gateway.mode = 'slow'
        started = time.monotonic()
        r = self.call('POST', '/auth/phone-otp/request/', json={'phone_number': PHONE, 'role': 'customer'})
        self.assertEqual(r.status_code, 503)
        self.assertLess(time.monotonic() - started, 2.5)              # 1s read timeout, not the 3s stall
        self.gateway.mode = 'ok'
        r = self.call('POST', '/auth/phone-otp/request/', json={'phone_number': PHONE, 'role': 'customer'})
        self.assertEqual(r.status_code, 200)
