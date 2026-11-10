from decimal import Decimal
from unittest.mock import MagicMock, patch

import razorpay
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari.constants import Constants
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption,
)
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.notifications.models.notification import Notification
from tests.test_customers import make_artist, make_customer, seed_payment_statuses

INITIATE = '/artists/registration/payment/initiate/'
VERIFY = '/artists/registration/payment/verify/'
SERVICE_GATEWAY = 'sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client'
VIEW_GATEWAY = 'sunndari_apps.artists.views.registration_payment.RazorpayGateway.get_client'


class VerifyRegistrationPaymentTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        self.client_, self.user, self.profile = make_artist(phone_number='+919100004001')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=False)
        self.gateway = MagicMock()
        self.orders = {}

        def create_order(data):
            order = {'id': f"order_{data['receipt']}", 'amount': data['amount'], 'amount_paid': 0,
                     'currency': data['currency'], 'status': 'created'}
            self.orders[order['id']] = order
            return order

        self.gateway.order.create.side_effect = create_order
        self.gateway.order.fetch.side_effect = lambda oid: self.orders[oid]
        self.gateway.utility.verify_payment_signature.return_value = None
        self.gateway.payment.refund.return_value = {'id': 'rfnd_1'}
        for target in (SERVICE_GATEWAY, VIEW_GATEWAY):
            patcher = patch(target, return_value=self.gateway)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _start(self, promo=None, client=None):
        body = {'promo_code': promo} if promo else {}
        resp = (client or self.client_).post(INITIATE, body, format='json')
        self.assertIn(resp.status_code, (200, 201), resp.data)
        return resp.data['data']['gateway_order_id']

    def _capture(self, order_id, amount=None, status='captured', payment_id='pay_1', currency='INR'):
        order = self.orders[order_id]
        if amount is not None:
            order['amount'] = amount            # a fully paid order, but for a different amount than we quoted
        order.update({'amount_paid': order['amount'], 'status': 'paid'})
        self.gateway.payment.fetch.side_effect = lambda pid: {
            'id': pid, 'order_id': order_id, 'status': status, 'currency': currency, 'amount': order['amount'],
        }

    def _verify(self, order_id, client=None, payment_id='pay_1'):
        return (client or self.client_).post(VERIFY, {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig',
        }, format='json')

    def _fee(self):
        return self.client_.get('/artists/registration/fee/').data['data']

    # --- success
    def test_a_verified_payment_marks_the_artist_paid_and_notifies(self):
        order_id = self._start()
        self.assertFalse(self._fee()['paid'])
        self._capture(order_id)
        resp = self._verify(order_id)
        self.assertEqual(resp.status_code, 200, resp.data)
        payment = ArtistRegistrationPayment.objects.get()
        self.assertEqual((payment.status.name, payment.gateway, payment.gateway_payment_id), ('paid', 'razorpay', 'pay_1'))
        self.assertIsNotNone(payment.paid_at)
        fee = self._fee()
        self.assertEqual((fee['paid'], fee['registrationRequired']), (True, False))
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)

    def test_a_discounted_payment_redeems_its_promo_only_after_verification(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        order_id = self._start('HALF')
        self.assertEqual(PromoRedemption.objects.get().status, 'reserved')
        self._capture(order_id)
        self._verify(order_id)
        self.assertEqual(PromoRedemption.objects.get().status, 'redeemed')
        self.assertEqual(ArtistRegistrationPayment.objects.get().payable_amount, Decimal('999.50'))

    def test_verifying_twice_is_safe_and_notifies_once(self):
        order_id = self._start()
        self._capture(order_id)
        self.assertEqual(self._verify(order_id).status_code, 200)
        again = self._verify(order_id)
        self.assertEqual((again.status_code, again.data['message']), (200, 'Payment already verified'))
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)

    def test_the_settlement_itself_is_idempotent(self):
        order_id = self._start()
        payment = ArtistRegistrationPayment.objects.get(gateway_order_id=order_id)
        outcomes = [RegistrationPaymentService.settle(payment.pk, 'pay_1') for _ in range(3)]
        self.assertEqual(outcomes, ['applied', 'already_applied', 'already_applied'])
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)

    # --- never trusts the client
    def test_a_bad_signature_does_not_mark_anything_paid(self):
        order_id = self._start()
        self._capture(order_id)
        self.gateway.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError('bad')
        resp = self._verify(order_id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.payment_signature_invalid, resp.data['message'])
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)
        self.assertFalse(self._fee()['paid'])

    def test_a_payment_the_gateway_has_not_captured_is_refused(self):
        order_id = self._start()
        self._capture(order_id, status='authorized')
        resp = self._verify(order_id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.payment_verification_mismatch, resp.data['message'])
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_a_wrong_amount_order_or_currency_is_refused(self):
        order_id = self._start()
        for tweak in (
            lambda: self._capture(order_id, amount=100),              # order amount does not match what we quoted
            lambda: self._capture(order_id, currency='USD'),
            lambda: self.gateway.payment.fetch.__setattr__('side_effect', lambda pid: {
                'id': pid, 'order_id': 'order_someone_else', 'status': 'captured', 'currency': 'INR'}),
        ):
            self.orders[order_id].update({'amount': 199900, 'amount_paid': 0, 'status': 'created'})
            tweak()
            resp = self._verify(order_id)
            self.assertEqual(resp.status_code, 400)
            self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_a_gateway_outage_during_verification_changes_nothing(self):
        order_id = self._start()
        self.gateway.payment.fetch.side_effect = razorpay.errors.ServerError('down')
        self.assertEqual(self._verify(order_id).status_code, 400)
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_another_artists_order_cannot_be_verified(self):
        order_id = self._start()
        self._capture(order_id)
        other_client, _, other = make_artist(phone_number='+919100004002')
        resp = self._verify(order_id, client=other_client)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.payment_not_found, resp.data['message'])
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)

    def test_unknown_order_and_unauthenticated_requests_are_refused(self):
        self.assertEqual(self._verify('order_nope').status_code, 400)
        self.assertEqual(APIClient().post(VERIFY, {}, format='json').status_code, 401)
        customer, _ = make_customer(phone_number='+919100004003')
        self.assertEqual(self._verify('order_nope', client=customer).status_code, 400)

    # --- duplicates and late captures
    def test_a_capture_for_a_replaced_attempt_is_refunded_when_the_fee_is_already_paid(self):
        first = self._start()                     # attempt 1, full fee
        PromoCode.objects.create(code='HALF', discount_percent=50)
        second = self._start('HALF')              # replaces attempt 1
        self._capture(second, payment_id='pay_2')
        self.assertEqual(self._verify(second, payment_id='pay_2').status_code, 200)
        # attempt 1 was paid at the gateway as well (the customer had the first checkout open)
        self._capture(first, payment_id='pay_1')
        first_payment = ArtistRegistrationPayment.objects.get(gateway_order_id=first)
        outcome = RegistrationPaymentService.settle(first_payment.pk, 'pay_1')
        self.assertEqual(outcome, 'refund_owed')
        self.gateway.payment.refund.assert_called_once_with('pay_1', {
            'amount': 199900, 'notes': {'registration_payment_id': str(first_payment.pk)},
        })
        first_payment.refresh_from_db()
        self.assertEqual((first_payment.status.name, first_payment.gateway_refund_id), ('refunded', 'rfnd_1'))
        self.assertEqual(ArtistRegistrationPayment.objects.filter(paid_at__isnull=False).count(), 1)

    def test_a_late_capture_for_a_replaced_attempt_is_honoured_if_nothing_else_was_paid(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        first = self._start('HALF')
        second = self._start()                    # replaces attempt 1 (its promo is released)
        self.assertEqual(PromoRedemption.objects.get().status, 'released')
        payment = ArtistRegistrationPayment.objects.get(gateway_order_id=first)
        self.assertEqual(RegistrationPaymentService.settle(payment.pk, 'pay_late'), 'applied')
        payment.refresh_from_db()
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(PromoRedemption.objects.get().status, 'redeemed')
        self.assertEqual(ArtistRegistrationPayment.objects.get(gateway_order_id=second).status.name, 'failed')

    def test_a_refund_that_fails_is_recorded_and_not_reported_as_returned(self):
        first = self._start()
        paid = ArtistRegistrationPayment.objects.get(gateway_order_id=first)
        RegistrationPaymentService.settle(paid.pk, 'pay_1')
        extra = ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999'), payable_amount=Decimal('1999'),
            status=paid.status.__class__.objects.get(name='pending'), gateway='razorpay', gateway_order_id='order_extra',
        )
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self.assertEqual(RegistrationPaymentService.settle(extra.pk, 'pay_x'), 'refund_owed')
        extra.refresh_from_db()
        self.assertEqual(extra.status.name, 'failed')
        self.assertIsNone(extra.gateway_refund_id)
        self.assertEqual((extra.refund_attempts, extra.refund_requested_at is not None), (1, True))
        self.assertIn('Refund failed', extra.failure_reason)

    def test_a_captured_payment_for_an_exempt_artist_is_refunded(self):
        order_id = self._start()
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        self._capture(order_id)
        resp = self._verify(order_id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_payment_not_applied, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.get().status.name, 'refunded')

    # --- 100% promo
    def test_a_100_percent_promo_notifies_and_needs_no_verification(self):
        PromoCode.objects.create(code='FREE', discount_percent=100)
        self.client_.post(INITIATE, {'promo_code': 'FREE'}, format='json')
        self.assertTrue(self._fee()['paid'])
        self.assertEqual(Notification.objects.filter(user_id=self.user.user_id, type='payment_status').count(), 1)
        self.gateway.order.create.assert_not_called()
