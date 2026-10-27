"""Hostile input against the surfaces added for payments, notifications and service activation. None of it may
crash (HTTP 5xx), leak internals, or change state it should not."""
import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.payments.models import Payment

from tests.test_customers import make_artist, make_customer

SECRET = 'whsec_fuzz'
WEBHOOK = '/customers/payments/webhook/razorpay/'
LEAKS = ('Traceback', 'File "/', 'sqlite3.', 'django.db.utils', '/Users/')


def post_signed(raw: bytes, secret=SECRET):
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return APIClient().generic('POST', WEBHOOK, raw, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=signature)


class WebhookFuzzTest(TestCase):

    def setUp(self):
        patcher = patch.object(Configurations, 'razorpay_webhook_secret', SECRET)
        patcher.start()
        self.addCleanup(patcher.stop)

    HOSTILE_EVENTS = [
        b'', b'null', b'[]', b'[1,2,3]', b'"text"', b'42', b'true', b'{', b'\xff\xfe\x00', b'{"event": null}',
        b'{"event": ["payment.captured"]}', b'{"event": "payment.captured"}', b'{"event": "payment.captured", "payload": null}',
        b'{"event": "payment.captured", "payload": "text"}', b'{"event": "payment.captured", "payload": []}',
        b'{"event": "payment.captured", "payload": {"payment": "text"}}',
        b'{"event": "payment.captured", "payload": {"payment": {"entity": "text"}}}',
        b'{"event": "payment.captured", "payload": {"payment": {"entity": null}}}',
        b'{"event": "payment.captured", "payload": {"payment": {"entity": {"id": 1, "order_id": 2, "amount": "x", "status": "captured"}}}}',
        b'{"event": "payment.captured", "payload": {"payment": {"entity": {"id": "p", "order_id": {"a": 1}, "amount": 1e999, "status": "captured"}}}}',
        b'{"event": "payment.captured", "payload": {"payment": {"entity": {"id": "p", "order_id": "' + b'A' * 5000 + b'", "amount": 1, "status": "captured"}}}}',
        b'{"event": "refund.processed", "payload": {"refund": "text"}}',
        b'{"event": "refund.processed", "payload": {"refund": {"entity": {"id": "r", "notes": "text"}}}}',
        b'{"event": "refund.processed", "payload": {"refund": {"entity": {"id": "r", "notes": {"payment_id": ["1"]}}}}}',
        b'{"event": "refund.processed", "payload": {"refund": {"entity": {"id": "r", "notes": {"payment_id": "99999999999999999999"}}}}}',
        b'{"event": "refund.failed", "payload": {"refund": null}}', b'{"event": "refund.failed", "payload": 5}',
        b'{"event": "' + b'x' * 100000 + b'"}', b'{"a":' * 500 + b'1' + b'}' * 500,
    ]

    def test_a_signed_but_malformed_event_is_acknowledged_not_answered_with_a_server_error(self):
        # A 5xx would make the gateway retry the same broken event for a day; malformed means "nothing to do".
        for raw in self.HOSTILE_EVENTS:
            resp = post_signed(raw)
            self.assertLess(resp.status_code, 500, raw[:80])
            self.assertNotIn(b'Traceback', resp.content, raw[:80])
        self.assertEqual(Payment.objects.count(), 0)

    def test_unsigned_or_wrongly_signed_events_are_refused_whatever_they_contain(self):
        for raw in self.HOSTILE_EVENTS[:12]:
            self.assertEqual(post_signed(raw, secret='another-secret').status_code, 400, raw[:60])
            self.assertEqual(APIClient().generic('POST', WEBHOOK, raw, content_type='application/json').status_code, 400)

    def test_odd_content_types_and_methods_are_handled(self):
        raw = b'{"event": "x"}'
        sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        for content_type in ('text/plain', 'application/xml', 'multipart/form-data; boundary=x', 'application/x-www-form-urlencoded'):
            resp = APIClient().generic('POST', WEBHOOK, raw, content_type=content_type, HTTP_X_RAZORPAY_SIGNATURE=sig)
            self.assertLess(resp.status_code, 500, content_type)
        for method in ('GET', 'PUT', 'DELETE', 'PATCH'):
            self.assertEqual(APIClient().generic(method, WEBHOOK, raw, HTTP_X_RAZORPAY_SIGNATURE=sig).status_code, 405)


class WebhookSignatureIndependenceTest(TestCase):
    """The signature check must not depend on the shared Razorpay client object (it once silently accepted everything
    when a test left a mock in place of it)."""

    EVENT = b'{"event": "payment.captured", "payload": {}}'

    def setUp(self):
        from sunndari_apps.payments.gateway import RazorpayGateway
        self.assertIsInstance(RazorpayGateway.__dict__['get_client'], classmethod,
                              'an earlier test left RazorpayGateway.get_client patched: stacked patches must be stopped in reverse order')

    def test_a_wrong_signature_is_refused_even_if_the_sdk_client_would_accept_anything(self):
        from unittest.mock import MagicMock
        accept_everything = MagicMock()
        with patch.object(Configurations, 'razorpay_webhook_secret', SECRET), \
                patch('sunndari_apps.payments.gateway.RazorpayGateway.get_client', return_value=accept_everything):
            for bad in ('', 'deadbeef', 'x' * 64, 'é' * 40, ' ', '0' * 63):
                resp = APIClient().generic('POST', WEBHOOK, self.EVENT, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=bad)
                self.assertEqual(resp.status_code, 400, bad)
        accept_everything.utility.verify_webhook_signature.assert_not_called()

    def test_the_correct_signature_is_accepted_in_any_letter_case_and_with_stray_spaces(self):
        sig = hmac.new(SECRET.encode(), self.EVENT, hashlib.sha256).hexdigest()
        with patch.object(Configurations, 'razorpay_webhook_secret', SECRET):
            for variant in (sig, sig.upper(), f' {sig} '):
                resp = APIClient().generic('POST', WEBHOOK, self.EVENT, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=variant)
                self.assertEqual(resp.status_code, 200, variant)

    def test_one_changed_byte_in_the_body_breaks_the_signature(self):
        sig = hmac.new(SECRET.encode(), self.EVENT, hashlib.sha256).hexdigest()
        with patch.object(Configurations, 'razorpay_webhook_secret', SECRET):
            tampered = self.EVENT.replace(b'captured', b'capturec')
            resp = APIClient().generic('POST', WEBHOOK, tampered, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=sig)
        self.assertEqual(resp.status_code, 400)


class WebhookRetrySemanticsTest(TestCase):

    def test_a_genuine_failure_on_our_side_still_answers_5xx_so_the_gateway_retries(self):
        event = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': 'pay_1', 'order_id': 'order_1', 'amount': 100, 'status': 'captured'}}}}).encode()
        with patch.object(Configurations, 'razorpay_webhook_secret', SECRET), \
                patch('sunndari_apps.payments.views.webhook.Payment.get_by_gateway_order_id', side_effect=RuntimeError('database is down')):
            self.assertEqual(post_signed(event).status_code, 500)


class PopupFuzzTest(TestCase):

    def test_hostile_queries_and_headers_never_crash_the_popup_endpoint(self):
        client, _, _ = make_artist(phone_number='+919990001001')
        customer_client, _ = make_customer(phone_number='+919990001002')
        url = '/core/service-sub-category/recently_activated/'
        for params in ({'days': '-1'}, {'days': 'abc'}, {'limit': '9' * 400}, {'page_num': '-9'}, {'values': 'x,y,z'},
                       {'sort_by': 'activated_at'}, {'filter_key': 'activated_at', 'filter_value': "' OR 1=1 --"},
                       {'search_key': '<script>'}, {'x': 'y' * 100000}):
            resp = client.get(url, params)
            self.assertLess(resp.status_code, 500, params)
            self.assertNotIn(b'Traceback', resp.content)
            self.assertLess(customer_client.get(url, params).status_code, 500, params)
        for header in ({'HTTP_AUTHORIZATION': 'Bearer ' + 'a' * 10000}, {'HTTP_AUTHORIZATION': 'Bearer'}, {'HTTP_X_FORWARDED_FOR': '\x00'},
                      {'HTTP_ACCEPT': '*/*;q=abc'}, {'HTTP_ACCEPT_LANGUAGE': 'zz-' * 500}):
            self.assertLess(APIClient().get(url, **header).status_code, 500, header)


class ServiceAdminFuzzTest(TestCase):

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username='fz', email='f@x.com', password='x')
        self.client.force_login(self.admin)
        self.category = ServiceCategory.objects.create(name='Makeup')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Bridal', is_active=False)
        self.url = reverse('admin:core_servicesubcategory_change', args=[self.service.pk])

    def test_hostile_form_input_is_rejected_cleanly_and_changes_nothing(self):
        for form in (
            {}, {'category': 'abc', 'name': 'x'}, {'category': '999999', 'name': 'x'}, {'category': self.category.pk, 'name': ''},
            {'category': self.category.pk, 'name': 'x' * 5000}, {'category': self.category.pk, 'name': 'x', 'is_active': ['on', 'off', '']},
            {'category': [self.category.pk, 999], 'name': 'x', 'is_active': 'on'}, {'category': self.category.pk, 'name': '\x00'},
            {'category': '-1', 'name': 'x'}, {'category': self.category.pk, 'name': 'Bridal', 'is_active': 'on',
                                              'activated_at': 'garbage', 'artists_announced_at': '2000-01-01', 'sub_category_id': '999'},
        ):
            resp = self.client.post(self.url, form)
            self.assertLess(resp.status_code, 500, form)
            for leak in LEAKS:
                self.assertNotContains(resp, leak, status_code=resp.status_code)
        self.service.refresh_from_db()
        self.assertEqual((self.service.name, self.service.category_id), ('Bridal', self.category.pk))

    def test_names_are_stored_as_text_and_escaped_when_shown(self):
        evil = '<script>alert(1)</script>'
        self.client.post(self.url, {'category': self.category.pk, 'name': evil, 'is_active': 'on'})
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, evil)                                    # stored verbatim ...
        page = self.client.get(reverse('admin:core_servicesubcategory_changelist'))
        self.assertNotContains(page, evil)                                           # ... never emitted unescaped
        self.assertContains(page, '&lt;script&gt;')

    def test_bulk_actions_with_empty_or_bogus_selections_do_nothing_and_do_not_crash(self):
        changelist = reverse('admin:core_servicesubcategory_changelist')
        # (A non-numeric id in a hand-crafted staff POST raises inside Django's own admin for every model, including
        # the untouched ones, so it is not exercised here.)
        for selected in ([], ['999999'], ['-1'], [str(self.service.pk)] * 5):
            for action in ('activate_selected', 'deactivate_selected', 'delete_selected', 'not_an_action'):
                resp = self.client.post(changelist, {'action': action, '_selected_action': selected}, follow=True)
                self.assertLess(resp.status_code, 500, (action, selected))
        self.service.refresh_from_db()
        self.assertTrue(ServiceSubCategory.objects.filter(pk=self.service.pk).exists())

    def test_duplicate_service_names_in_a_category_are_refused_not_crashed(self):
        ServiceSubCategory.objects.create(category=self.category, name='Party')
        resp = self.client.post(self.url, {'category': self.category.pk, 'name': 'Party', 'is_active': 'on'})
        self.assertEqual(resp.status_code, 200)                                       # form re-shown with the error
        self.assertContains(resp, 'already exists')
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, 'Bridal')
