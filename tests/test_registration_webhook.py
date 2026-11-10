"""Registration-fee payments through the Razorpay webhook and the reconcile job. The booking cases of both are
covered in test_payment_reliability; these check the registration path and that it never disturbs bookings."""
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.tasks import reconcile_pending_payments
from tests.test_customers import make_artist, seed_payment_statuses

WEBHOOK = '/customers/payments/webhook/razorpay/'
INITIATE = '/artists/registration/payment/initiate/'
SECRET = 'whsec_test_secret'
SERVICE_GATEWAY = 'sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client'
TASK_GATEWAY = 'sunndari_apps.payments.tasks.RazorpayGateway.get_client'


class RegistrationWebhookTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        self.client_, self.user, self.profile = make_artist(phone_number='+919100005001')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=False)
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {'id': f"order_{data['receipt']}"}
        self.gateway.payment.refund.return_value = {'id': 'rfnd_1'}
        for target in (SERVICE_GATEWAY, TASK_GATEWAY):
            patcher = patch(target, return_value=self.gateway)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(Configurations, 'razorpay_webhook_secret', SECRET)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start(self, promo=None):
        resp = self.client_.post(INITIATE, {'promo_code': promo} if promo else {}, format='json')
        self.assertIn(resp.status_code, (200, 201), resp.data)
        return resp.data['data']['gateway_order_id'], resp.data['data']['amount']

    def _post(self, body, secret=SECRET):
        raw = json.dumps(body).encode()
        return APIClient().generic('POST', WEBHOOK, raw, content_type='application/json',
                                   HTTP_X_RAZORPAY_SIGNATURE=hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest())

    def _captured(self, order_id, paise, payment_id='pay_wh', currency='INR'):
        return {'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': payment_id, 'order_id': order_id, 'amount': paise, 'status': 'captured', 'currency': currency}}}}

    def _fee(self):
        return self.client_.get('/artists/registration/fee/').data['data']

    # --- webhook
    def test_a_captured_webhook_settles_the_registration_without_the_app(self):
        order_id, paise = self._start()
        self.assertEqual(self._post(self._captured(order_id, paise)).status_code, 200)
        payment = ArtistRegistrationPayment.objects.get()
        self.assertEqual((payment.status.name, payment.gateway_payment_id), ('paid', 'pay_wh'))
        self.assertTrue(self._fee()['paid'])
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)

    def test_a_repeated_or_reordered_webhook_changes_nothing_more(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        order_id, paise = self._start('HALF')
        for _ in range(3):
            self.assertEqual(self._post(self._captured(order_id, paise)).status_code, 200)
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)
        self.assertEqual(PromoRedemption.objects.get().status, 'redeemed')
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)

    def test_the_webhook_and_the_app_verify_can_both_report_the_same_payment(self):
        order_id, paise = self._start()
        self._post(self._captured(order_id, paise))
        payment = ArtistRegistrationPayment.objects.get()
        from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
        self.assertEqual(RegistrationPaymentService.settle(payment.pk, 'pay_wh'), 'already_applied')
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)

    def test_a_wrong_amount_or_currency_is_ignored(self):
        order_id, paise = self._start()
        self.assertEqual(self._post(self._captured(order_id, paise - 100)).status_code, 200)
        self.assertEqual(self._post(self._captured(order_id, paise, currency='USD')).status_code, 200)
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_a_forged_webhook_is_rejected_and_changes_nothing(self):
        order_id, paise = self._start()
        self.assertEqual(self._post(self._captured(order_id, paise), secret='wrong').status_code, 400)
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_an_authorized_but_uncaptured_event_is_ignored(self):
        order_id, paise = self._start()
        event = self._captured(order_id, paise)
        event['payload']['payment']['entity']['status'] = 'authorized'
        self.assertEqual(self._post(event).status_code, 200)
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_a_webhook_capture_for_an_already_paid_artist_is_refunded(self):
        first, first_paise = self._start()
        self._post(self._captured(first, first_paise, payment_id='pay_1'))
        extra = ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999'), payable_amount=Decimal('1999'), gateway='razorpay',
            gateway_order_id='order_extra', status=ArtistRegistrationPayment.objects.get().status.__class__.objects.get(name='pending'),
        )
        self.assertEqual(self._post(self._captured('order_extra', 199900, payment_id='pay_2')).status_code, 200)
        extra.refresh_from_db()
        self.assertEqual((extra.status.name, extra.gateway_refund_id), ('refunded', 'rfnd_1'))
        self.gateway.payment.refund.assert_called_once()
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)

    def test_a_refund_processed_event_closes_a_registration_refund(self):
        order_id, paise = self._start()
        self._post(self._captured(order_id, paise))
        payment = ArtistRegistrationPayment.objects.get()
        event = {'event': 'refund.processed', 'payload': {'refund': {'entity': {
            'id': 'rfnd_hook', 'notes': {'registration_payment_id': str(payment.pk)}}}}}
        self.assertEqual(self._post(event).status_code, 200)
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', 'rfnd_hook'))
        self.assertEqual(self._post(event).status_code, 200)             # a repeat is a no-op

    def test_an_unknown_order_is_acknowledged_and_ignored(self):
        self.assertEqual(self._post(self._captured('order_nobody', 100)).status_code, 200)
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)

    # --- reconcile
    def _gateway_has_paid(self, order_id, paise, payment_id='pay_rec'):
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': paise, 'status': 'paid'}
        self.gateway.order.payments.return_value = {'items': [{'id': payment_id, 'order_id': order_id, 'status': 'captured'}]}

    def _age(self, minutes):
        ArtistRegistrationPayment.objects.update(created_at=timezone.now() - timedelta(minutes=minutes))

    def test_a_payment_the_app_never_confirmed_is_settled_by_the_reconcile_job(self):
        order_id, paise = self._start()
        self._gateway_has_paid(order_id, paise)
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 1)
        self.assertTrue(self._fee()['paid'])
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)
        self.assertEqual(reconcile_pending_payments(), 0)                  # nothing left to do

    def test_a_fresh_or_unpaid_registration_is_left_alone(self):
        order_id, paise = self._start()
        self._gateway_has_paid(order_id, paise)
        self.assertEqual(reconcile_pending_payments(), 0)                  # too new: verify is still the fast path
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': 0, 'status': 'created'}
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 0)
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_a_replaced_attempt_that_was_paid_is_recovered_by_reconcile(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        first, paise = self._start('HALF')
        self._start()                                                       # replaces it; the first is now 'failed'
        self.assertEqual(ArtistRegistrationPayment.objects.get(gateway_order_id=first).status.name, 'failed')
        self._gateway_has_paid(first, paise)
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 1)
        self.assertTrue(self._fee()['paid'])

    def test_a_late_payment_for_an_already_paid_artist_is_refunded_by_reconcile(self):
        first, first_paise = self._start()
        self._post(self._captured(first, first_paise))
        extra = ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999'), payable_amount=Decimal('1999'), gateway='razorpay',
            gateway_order_id='order_late', status=ArtistRegistrationPayment.objects.get().status.__class__.objects.get(name='pending'),
        )
        self._gateway_has_paid('order_late', 199900, payment_id='pay_late')
        self._age(30)
        self.assertEqual(reconcile_pending_payments(), 1)
        extra.refresh_from_db()
        self.assertEqual(extra.status.name, 'refunded')
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)
