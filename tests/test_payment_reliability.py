"""Webhook, scheduled refund retry and reconciliation: the parts of the payment flow that must work when the
customer's phone or the gateway misbehaves. Every test asserts the safe outcome."""
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.customers.models import Booking
from sunndari_apps.customers.tasks import cancel_stale_pending_bookings
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.payments.tasks import reconcile_pending_payments, retry_owed_refunds
from tests.test_failure_modes import GatewayFixture
from tests.test_customers import make_user

WEBHOOK = '/customers/payments/webhook/razorpay/'
SECRET = 'whsec_test_secret'


def signed(body: dict, secret: str = SECRET):
    raw = json.dumps(body).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class _Flow(GatewayFixture, TestCase):
    """Reuses the booking + mocked-gateway fixture of the failure-mode tests."""

    def post_webhook(self, body, secret=SECRET, signature=None):
        raw, good = signed(body, secret)
        return APIClient().generic('POST', WEBHOOK, raw, content_type='application/json',
                                   HTTP_X_RAZORPAY_SIGNATURE=good if signature is None else signature)

    def captured_event(self, order_id, paise, payment_id='pay_wh'):
        return {'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': payment_id, 'order_id': order_id, 'amount': paise, 'status': 'captured'}}}}

    def open_order(self):
        resp = self._initiate()
        return resp.data['data']['gateway_order_id'], resp.data['data']['amount']


class WebhookTest(_Flow):

    def setUp(self):
        super().setUp()
        patcher = patch.object(Configurations, 'razorpay_webhook_secret', SECRET)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_a_configured_secret_nothing_is_accepted(self):
        with patch.object(Configurations, 'razorpay_webhook_secret', ''):
            order_id, paise = self.open_order()
            resp = self.post_webhook(self.captured_event(order_id, paise))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_a_forged_or_unsigned_webhook_changes_nothing(self):
        order_id, paise = self.open_order()
        event = self.captured_event(order_id, paise)
        for secret, signature in (('wrong-secret', None), (SECRET, 'deadbeef'), (SECRET, '')):
            resp = self.post_webhook(event, secret=secret, signature=signature)
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_a_signed_capture_settles_the_payment_even_if_the_app_never_called_verify(self):
        order_id, paise = self.open_order()
        resp = self.post_webhook(self.captured_event(order_id, paise))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), Decimal('2000.00'))
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='payment_status').exists())

    def test_repeated_and_reordered_deliveries_are_harmless(self):
        order_id, paise = self.open_order()
        for _ in range(3):
            self.assertEqual(self.post_webhook(self.captured_event(order_id, paise)).status_code, 200)
        self._gateway_says_paid(order_id, paise, payment_id='pay_wh')
        self.assertEqual(self._verify(order_id, payment_id='pay_wh').status_code, 200)       # app verifies afterwards
        self.assertEqual(Payment.objects.filter(booking_id=self.booking_id, status__name='paid').count(), 1)
        self.assertEqual(Notification.objects.filter(user_id=self.customer.user_id, type='payment_status').count(), 1)   # told once, not per delivery

    def test_a_capture_with_the_wrong_amount_is_ignored(self):
        order_id, paise = self.open_order()
        self.post_webhook(self.captured_event(order_id, paise - 100))
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_a_capture_for_an_unknown_order_or_a_non_captured_payment_is_acknowledged_and_ignored(self):
        self.assertEqual(self.post_webhook(self.captured_event('order_nobody', 100)).status_code, 200)
        order_id, paise = self.open_order()
        event = self.captured_event(order_id, paise)
        event['payload']['payment']['entity']['status'] = 'authorized'
        self.assertEqual(self.post_webhook(event).status_code, 200)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), 0)

    def test_an_unknown_event_type_is_acknowledged_so_the_gateway_stops_retrying(self):
        self.assertEqual(self.post_webhook({'event': 'something.new', 'payload': {}}).status_code, 200)

    def test_a_late_capture_for_a_cancelled_booking_is_refunded_not_kept(self):
        order_id, paise = self.open_order()
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        self.assertEqual(self.post_webhook(self.captured_event(order_id, paise)).status_code, 200)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'refunded')
        self.assertEqual(self.gateway.payment.refund.call_count, 1)
        self.post_webhook(self.captured_event(order_id, paise))                               # redelivery
        self.assertEqual(self.gateway.payment.refund.call_count, 1)

    def test_a_refund_processed_event_closes_a_refund_whose_reply_was_lost(self):
        self._pay()
        self.gateway.payment.refund.side_effect = Exception('timeout')
        self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        payment = Payment.objects.get(booking_id=self.booking_id)
        self.assertEqual(payment.status.name, 'paid')
        event = {'event': 'refund.processed', 'payload': {'refund': {'entity': {
            'id': 'rfnd_1', 'payment_id': 'pay_ok', 'amount': 200000, 'notes': {'payment_id': str(payment.payment_id)}}}}}
        self.assertEqual(self.post_webhook(event).status_code, 200)
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', 'rfnd_1'))

    def test_refunds_not_made_by_this_system_are_left_alone(self):
        self._pay()
        event = {'event': 'refund.processed', 'payload': {'refund': {'entity': {
            'id': 'rfnd_manual', 'payment_id': 'pay_ok', 'amount': 200000, 'notes': {}}}}}
        self.assertEqual(self.post_webhook(event).status_code, 200)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'paid')


class RefundRetryJobTest(_Flow):

    def _owed(self):
        self._pay()
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        return Payment.objects.get(booking_id=self.booking_id)

    def test_the_job_is_scheduled(self):
        from django.conf import settings
        tasks = [entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertIn('sunndari_apps.payments.tasks.retry_owed_refunds', tasks)
        self.assertIn('sunndari_apps.payments.tasks.reconcile_pending_payments', tasks)

    def test_a_failed_refund_is_retried_automatically_once_the_backoff_has_passed(self):
        payment = self._owed()
        self.assertEqual((payment.status.name, payment.refund_attempts), ('paid', 1))
        self.gateway.payment.refund.side_effect = None
        self.assertEqual(retry_owed_refunds()['waiting'], 1)                                  # too soon: backing off
        Payment.objects.filter(pk=payment.pk).update(refund_last_attempt_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(retry_owed_refunds()['refunded'], 1)
        self.assertEqual(Payment.objects.get(pk=payment.pk).status.name, 'refunded')

    def test_backoff_grows_with_each_failure(self):
        payment = self._owed()
        for attempts, waited_minutes, expected in ((1, 1, 'waiting'), (1, 3, 'pending'), (4, 10, 'waiting'), (4, 20, 'pending')):
            Payment.objects.filter(pk=payment.pk).update(
                refund_attempts=attempts, refund_last_attempt_at=timezone.now() - timedelta(minutes=waited_minutes))
            self.assertEqual(retry_owed_refunds()[expected], 1, (attempts, waited_minutes))

    def test_after_the_last_attempt_the_admins_are_told_once_and_retries_stop(self):
        admin = make_user('+919200000099', 'admin', 'Ops')
        payment = self._owed()
        Payment.objects.filter(pk=payment.pk).update(
            refund_attempts=Configurations.refund_max_attempts, refund_last_attempt_at=timezone.now() - timedelta(days=1))
        calls = self.gateway.payment.refund.call_count
        for _ in range(3):
            self.assertEqual(retry_owed_refunds()['escalated'], 1)
        self.assertEqual(self.gateway.payment.refund.call_count, calls)
        self.assertEqual(Notification.objects.filter(user_id=admin.user_id, title='Refund needs manual attention').count(), 1)

    def test_a_refund_that_succeeded_is_never_picked_up_again(self):
        self._pay()
        self.client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        calls = self.gateway.payment.refund.call_count
        for _ in range(3):
            retry_owed_refunds()
        self.assertEqual(self.gateway.payment.refund.call_count, calls)

    def test_a_gateway_capture_that_could_not_be_applied_is_also_retried(self):
        order_id, paise = self.open_order()
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self._gateway_says_paid(order_id, paise)
        self._verify(order_id)
        payment = Payment.objects.get(booking_id=self.booking_id)
        self.assertEqual((payment.status.name, payment.refund_attempts), ('failed', 1))
        self.gateway.payment.refund.side_effect = None
        Payment.objects.filter(pk=payment.pk).update(refund_last_attempt_at=timezone.now() - timedelta(hours=1))
        retry_owed_refunds()
        self.assertEqual(Payment.objects.get(pk=payment.pk).status.name, 'refunded')


class ReconciliationTest(_Flow):

    def _age(self, minutes):
        Payment.objects.filter(booking_id=self.booking_id).update(created_at=timezone.now() - timedelta(minutes=minutes))

    def _gateway_has_paid(self, order_id, paise):
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': paise, 'status': 'paid'}
        self.gateway.order.payments.return_value = {'items': [{'id': 'pay_rec', 'order_id': order_id, 'status': 'captured'}]}

    def test_a_payment_the_app_never_confirmed_is_settled_from_the_gateway(self):
        order_id, paise = self.open_order()
        self._gateway_has_paid(order_id, paise)
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 1)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), Decimal('2000.00'))
        self.assertEqual(reconcile_pending_payments(), 0)                                      # nothing left to do

    def test_a_fresh_payment_is_left_for_verify_to_handle(self):
        order_id, paise = self.open_order()
        self._gateway_has_paid(order_id, paise)
        self.assertEqual(reconcile_pending_payments(), 0)

    def test_an_order_the_customer_never_paid_stays_pending(self):
        order_id, paise = self.open_order()
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': 0, 'status': 'created'}
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 0)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'pending')

    def test_a_payment_wrongly_marked_failed_while_still_authorized_recovers(self):
        order_id, paise = self.open_order()
        self.gateway.payment.fetch.return_value = {'id': 'pay_rec', 'order_id': order_id, 'status': 'authorized', 'amount': paise}
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': 0, 'status': 'attempted'}
        self.assertEqual(self._verify(order_id, payment_id='pay_rec').status_code, 400)
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'failed')
        self._gateway_has_paid(order_id, paise)                                                # captured a moment later
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 1)
        self.assertEqual(Payment.total_settled_for_booking(booking_id=self.booking_id), Decimal('2000.00'))

    def test_a_late_payment_found_by_reconciliation_is_refunded(self):
        order_id, paise = self.open_order()
        Booking.objects.filter(booking_id=self.booking_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        cancel_stale_pending_bookings()
        self._gateway_has_paid(order_id, paise)
        self._age(30)
        reconcile_pending_payments()
        self.assertEqual(Payment.objects.get(booking_id=self.booking_id).status.name, 'refunded')

    def test_a_gateway_error_for_one_order_does_not_stop_the_run(self):
        order_id, paise = self.open_order()
        self.gateway.order.fetch.side_effect = Exception('gateway 502')
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 0)
