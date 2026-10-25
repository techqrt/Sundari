"""Email through Brevo SMTP: the transport (TLS, timeouts, error mapping), the messages, every place that sends a
one-time code, and the email copy of account notifications. The test runner swaps in Django's in-memory mail backend,
so these tests send nothing; live delivery is checked with `manage.py send_test_email`."""
import smtplib
import socket
import ssl
from io import StringIO
from unittest.mock import patch

from celery.exceptions import Retry
from django.conf import settings
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.authentication.models import User
from sunndari_apps.common.emailing import (
    CertifiSMTPEmailBackend, EmailDeliveryError, notification_message, otp_message, send_email,
)
from sunndari_apps.notifications.email_channel import EMAIL_NOTIFICATION_TYPES
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.tasks import send_notification_email
from sunndari_apps.notifications.utils import NotificationService

from tests.test_customers import make_customer, make_user

SECRET = 'xsmtpsib-THIS-MUST-NEVER-APPEAR-IN-A-LOG'


# ─── Transport ────────────────────────────────────────────────────────────────

class TransportTest(TestCase):

    def test_the_server_certificate_is_verified_against_a_bundle_that_does_not_depend_on_the_host(self):
        context = CertifiSMTPEmailBackend().ssl_context
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)               # verification is on ...
        self.assertTrue(context.check_hostname)                                 # ... including the host name
        self.assertGreater(len(context.get_ca_certs()), 50)                     # ... against real authorities

    def test_the_trusted_authorities_come_from_certifi_whatever_the_host_provides(self):
        import certifi
        with patch('sunndari_apps.common.emailing.ssl.create_default_context', return_value=ssl.create_default_context()) as create:
            CertifiSMTPEmailBackend().ssl_context
        create.assert_called_once_with(cafile=certifi.where())

    def test_the_shipped_configuration_points_at_brevo_with_tls_and_a_timeout(self):
        from decouple import config
        if config('EMAIL_HOST', default='') == '':
            self.assertEqual(settings.EMAIL_HOST, 'smtp-relay.brevo.com')
        self.assertEqual((settings.EMAIL_PORT, settings.EMAIL_USE_TLS), (587, True))
        self.assertTrue(0 < settings.EMAIL_TIMEOUT <= 60, 'a stalled mail server must not hang a request forever')
        self.assertTrue(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)

    def test_the_configured_backend_is_the_safe_one_even_though_tests_run_on_the_in_memory_one(self):
        from decouple import config
        self.assertEqual(config('EMAIL_BACKEND', default='sunndari_apps.common.emailing.CertifiSMTPEmailBackend'),
                         'sunndari_apps.common.emailing.CertifiSMTPEmailBackend')

    def test_certifi_is_a_declared_dependency(self):
        self.assertIn('certifi', open(settings.BASE_DIR / 'requirements.txt').read())


class SendEmailTest(TestCase):

    def test_a_message_goes_out_as_text_plus_html_from_the_configured_sender(self):
        send_email(to='asha@example.com', subject='Hello', text='plain body', html_body='<p>html body</p>', tag='otp')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject, message.from_email), (['asha@example.com'], 'Hello', settings.DEFAULT_FROM_EMAIL))
        self.assertEqual(message.body, 'plain body')
        self.assertEqual(message.alternatives[0].content, '<p>html body</p>')
        self.assertEqual(message.alternatives[0].mimetype, 'text/html')
        self.assertEqual(message.extra_headers['X-Mailin-Tag'], 'otp')           # Brevo groups its reports by this

    def test_every_kind_of_delivery_failure_becomes_one_error_with_nothing_sensitive_in_it(self):
        failures = [
            smtplib.SMTPAuthenticationError(535, b'authentication failed'), smtplib.SMTPAuthenticationError(525, b'Unauthorized IP address'),
            smtplib.SMTPServerDisconnected('gone'), smtplib.SMTPRecipientsRefused({'x': (550, b'no')}),
            smtplib.SMTPSenderRefused(550, b'sender not verified', 'a@b.c'), smtplib.SMTPDataError(554, b'rejected'),
            socket.timeout('timed out'), ConnectionRefusedError('refused'), TimeoutError('slow'),
            ssl.SSLCertVerificationError('bad certificate'), ValueError('Header values can’t contain newlines'),
        ]
        for failure in failures:
            with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=failure):
                with self.assertRaises(EmailDeliveryError) as raised:
                    send_email(to='victim@example.com', subject='Secret subject', text='code 424242')
            self.assertEqual(str(raised.exception), '', type(failure).__name__)
            self.assertIsNone(raised.exception.__cause__)

    def test_a_server_that_accepts_no_recipient_is_a_failure(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', return_value=0):
            with self.assertRaises(EmailDeliveryError):
                send_email(to='a@example.com', subject='s', text='t')

    @override_settings(EMAIL_HOST_PASSWORD=SECRET)
    def test_logs_name_the_problem_but_never_contain_the_key_the_address_or_the_message(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send',
                   side_effect=smtplib.SMTPAuthenticationError(525, b'5.7.1 Unauthorized IP address')):
            with self.assertLogs('sunndari_apps.common.emailing', level='WARNING') as logs:
                with self.assertRaises(EmailDeliveryError):
                    send_email(to='victim@example.com', subject='Subject 777', text='your code is 424242')
        output = '\n'.join(logs.output)
        self.assertIn('SMTPAuthenticationError', output)
        self.assertIn('525', output)
        for secret in (SECRET, 'victim@example.com', '424242', 'Subject 777'):
            self.assertNotIn(secret, output)


# ─── Messages ─────────────────────────────────────────────────────────────────

class MessageTest(TestCase):

    def test_the_code_email_carries_the_code_the_validity_and_a_warning(self):
        subject, text, page = otp_message(424242, 10)
        self.assertEqual(subject, 'Your SUNNDARI verification code')
        for body in (text, page):
            self.assertIn('424242', body)
            self.assertIn('10 minutes', body)
        self.assertIn('Never share it', text)
        self.assertNotIn('<script', page.lower())
        self.assertNotIn('http', page.lower().replace('http-equiv', ''))        # no remote images or trackers

    def test_anything_dynamic_is_escaped_in_the_html_and_left_alone_in_the_text(self):
        subject, text, page = notification_message('<b>Hi</b> & welcome', '<script>alert(1)</script> "quoted"')
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('&lt;b&gt;Hi&lt;/b&gt; &amp; welcome', page)
        self.assertIn('<script>alert(1)</script>', text)                         # plain text is not interpreted by a client
        self.assertEqual(subject, '<b>Hi</b> & welcome')

    def test_the_validity_shown_follows_the_configured_otp_lifetime(self):
        from sunndari_apps.authentication.utils import send_otp_email
        with patch.object(Configurations, 'otp_expiry_minutes', 7):
            send_otp_email('asha@example.com', 123456)
        self.assertIn('7 minutes', mail.outbox[0].body)


# ─── Every place a code is emailed ────────────────────────────────────────────

class OtpEmailFlowTest(TestCase):
    REQUEST = '/auth/email-otp/request/'

    def setUp(self):
        self.client = APIClient()

    def ask(self, email='asha@example.com'):
        return self.client.post(self.REQUEST, {'email': email, 'role': 'customer'}, format='json')

    def test_the_sign_in_code_is_emailed_and_matches_the_one_the_server_will_accept(self):
        self.assertEqual(self.ask().status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        code = User.objects.get(email='asha@example.com').otp
        self.assertIn(str(code), mail.outbox[0].body)
        verify = self.client.post('/auth/email-otp/verify/', {'email': 'asha@example.com', 'otp': str(code)}, format='json')
        self.assertEqual(verify.status_code, 200)

    def test_asking_again_within_a_minute_sends_nothing_more(self):
        self.ask()
        self.assertEqual(self.ask().status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    def test_when_the_mail_server_refuses_the_user_is_told_and_the_code_is_dropped(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected()):
            resp = self.ask()
        self.assertEqual(resp.status_code, 503)
        self.assertIn('try again', resp.data['message'].lower())
        user = User.objects.get(email='asha@example.com')
        self.assertIsNone(user.otp)
        self.assertEqual(self.ask().status_code, 200)                              # no cooldown trap: retry works at once
        self.assertEqual(len(mail.outbox), 1)

    def test_a_code_that_was_never_delivered_cannot_be_guessed_into_a_session(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=OSError()):
            self.ask()
        resp = self.client.post('/auth/email-otp/verify/', {'email': 'asha@example.com', 'otp': '123456'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_forgot_password_answers_the_same_for_known_unknown_and_failing_addresses(self):
        user = make_user('+919400000001', 'customer')
        User.objects.filter(pk=user.pk).update(email='known@example.com')
        known = self.client.post('/auth/forgot-password/', {'username': 'known@example.com'}, format='json')
        unknown = self.client.post('/auth/forgot-password/', {'username': 'nobody@example.com'}, format='json')
        self.assertEqual((known.status_code, known.data['message']), (unknown.status_code, unknown.data['message']))
        self.assertEqual([m.to for m in mail.outbox], [['known@example.com']])           # only the real account was emailed
        User.objects.filter(pk=user.pk).update(otp=None, otp_expiry=None)
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected()):
            failing = self.client.post('/auth/forgot-password/', {'username': 'known@example.com'}, format='json')
        self.assertEqual((failing.status_code, failing.data['message']), (known.status_code, known.data['message']))

    def test_changing_the_email_sends_the_code_to_the_new_address_only(self):
        client, user = make_customer(phone_number='+919400000002')
        User.objects.filter(pk=user.pk).update(email='old@example.com')
        resp = client.post('/users/contact/change/request/', {'email': 'new@example.com'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([m.to for m in mail.outbox], [['new@example.com']])

    def test_if_that_email_fails_the_pending_change_is_dropped_and_can_be_retried_at_once(self):
        client, user = make_customer(phone_number='+919400000003')
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected()):
            resp = client.post('/users/contact/change/request/', {'email': 'new@example.com'}, format='json')
        self.assertEqual(resp.status_code, 503)
        user.refresh_from_db()
        self.assertIsNone(user.pending_email)
        self.assertIsNone(user.contact_otp)
        retry = client.post('/users/contact/change/request/', {'email': 'new@example.com'}, format='json')
        self.assertEqual(retry.status_code, 200)

    def test_the_one_time_code_never_reaches_the_logs_when_sending_fails(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=smtplib.SMTPServerDisconnected()):
            with self.assertLogs(level='WARNING') as logs:
                self.ask()
        code_free = '\n'.join(logs.output)
        self.assertNotIn('asha@example.com', code_free)


# ─── Email copies of notifications ────────────────────────────────────────────

class NotificationEmailTest(TestCase):

    def setUp(self):
        self.user = make_user('+919400000010', 'customer')
        User.objects.filter(pk=self.user.pk).update(email='asha@example.com')

    def notify(self, type='booking_confirmed', user=None, **extra):
        """Creates the notification and lets its commit hook run, with the queue replaced by running the job in-line."""
        with patch('sunndari_apps.common.queueing.enqueue', side_effect=lambda task, *a: task(*a)):
            with self.captureOnCommitCallbacks(execute=True):
                return NotificationService.notify(
                    user_id=(user or self.user).user_id, title='Booking confirmed', message='Your booking on 12 Oct is confirmed.',
                    type=type, **extra)

    def test_an_account_notification_is_emailed_with_its_own_title_and_message(self):
        notification_id = self.notify()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (['asha@example.com'], 'Booking confirmed'))
        self.assertIn('Your booking on 12 Oct is confirmed.', message.body)
        self.assertIsNotNone(Notification.objects.get(pk=notification_id).email_sent_at)

    def test_only_the_listed_transactional_types_are_ever_emailed(self):
        for type in ('service_activated', 'start_pin_ready', 'completion_pin_ready', 'booking_otp_issued', 'artist_on_the_way',
                     'artist_arrived', 'service_started', 'generic', 'help_center_customer_message', 'help_center_artist_message'):
            self.notify(type=type)
        self.assertEqual(mail.outbox, [])

    def test_nothing_that_carries_or_prompts_a_code_is_on_the_list(self):
        for type in EMAIL_NOTIFICATION_TYPES:
            self.assertNotIn('pin', type)
            self.assertNotIn('otp', type)
        self.assertNotIn('service_activated', EMAIL_NOTIFICATION_TYPES)                   # promotional: needs opt-in

    def test_users_without_an_email_or_deactivated_ones_get_none(self):
        phone_only = make_user('+919400000011', 'customer')
        self.notify(user=phone_only)
        gone = make_user('+919400000012', 'customer')
        User.objects.filter(pk=gone.pk).update(email='gone@example.com', is_active=False)
        self.notify(user=gone)
        self.assertEqual(mail.outbox, [])

    def test_the_master_switch_turns_it_off(self):
        with patch.object(Configurations, 'email_notifications_enabled', False):
            self.notify()
        self.assertEqual(mail.outbox, [])

    def test_a_duplicated_job_emails_only_once(self):
        notification_id = self.notify()
        self.assertEqual(send_notification_email(notification_id), 'already sent')
        self.assertEqual(send_notification_email(notification_id), 'already sent')
        self.assertEqual(len(mail.outbox), 1)

    def test_a_mail_failure_hands_the_claim_back_so_the_retry_can_finish(self):
        with patch('sunndari_apps.common.queueing.enqueue'):                       # create it without sending yet
            with self.captureOnCommitCallbacks(execute=True):
                notification_id = NotificationService.notify(
                    user_id=self.user.user_id, title='Refund initiated', message='A refund of Rs 500 has been initiated.', type='refund_initiated')
        with patch('sunndari_apps.notifications.tasks.send_email', side_effect=EmailDeliveryError()):
            with self.assertRaises((EmailDeliveryError, Retry)):
                send_notification_email(notification_id)
        self.assertIsNone(Notification.objects.get(pk=notification_id).email_sent_at)
        self.assertEqual(send_notification_email(notification_id), 'sent')
        self.assertEqual(len(mail.outbox), 1)

    def test_email_problems_never_affect_the_notification_itself(self):
        queued = []
        with patch('sunndari_apps.common.queueing.enqueue', side_effect=lambda task, *a: queued.append((task, a))):
            with self.captureOnCommitCallbacks(execute=True):
                notification_id = NotificationService.notify(
                    user_id=self.user.user_id, title='t', message='m', type='booking_confirmed')
        self.assertEqual(len(queued), 1)                                           # queued after the commit, not run in the request
        with patch('sunndari_apps.notifications.tasks.send_email', side_effect=EmailDeliveryError()):
            with self.assertRaises((EmailDeliveryError, Retry)):
                queued[0][0](*queued[0][1])                                        # the worker's attempt fails ...
        notification = Notification.objects.get(pk=notification_id)                # ... the notification is untouched
        self.assertEqual((notification.title, notification.message, notification.is_read), ('t', 'm', False))

    def test_a_dead_job_queue_does_not_break_creating_the_notification(self):
        with patch('sunndari_apps.notifications.tasks.send_notification_email.apply_async', side_effect=ConnectionError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                notification_id = NotificationService.notify(
                    user_id=self.user.user_id, title='t', message='m', type='booking_confirmed')
        self.assertIsNotNone(notification_id)
        self.assertEqual(mail.outbox, [])


# ─── The delivery check command ───────────────────────────────────────────────

class SendTestEmailCommandTest(TestCase):

    def test_it_sends_one_message_to_the_address_given(self):
        out = StringIO()
        call_command('send_test_email', 'owner@example.com', stdout=out)
        self.assertEqual([m.to for m in mail.outbox], [['owner@example.com']])
        self.assertIn('Accepted by the mail server', out.getvalue())

    def test_a_refusal_is_reported_without_any_credential(self):
        with patch('sunndari_apps.common.emailing.EmailMultiAlternatives.send', side_effect=smtplib.SMTPAuthenticationError(525, b'Unauthorized IP address')):
            with self.assertRaises(CommandError) as raised:
                call_command('send_test_email', 'owner@example.com', stdout=StringIO())
        self.assertNotIn(settings.EMAIL_HOST_PASSWORD, str(raised.exception))
        self.assertIn('verified sender', str(raised.exception))

    def test_an_address_without_an_at_sign_is_refused_before_anything_is_sent(self):
        with self.assertRaises(CommandError):
            call_command('send_test_email', 'not-an-address', stdout=StringIO())
        self.assertEqual(mail.outbox, [])
