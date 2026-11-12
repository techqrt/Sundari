"""An admin rejection returns the registration fee; the artist pays again to resubmit. Free (100% promo)
registrations only release the promo. A failed refund is retried with backoff and escalated, never lost."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from sunndari.config import Configurations
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.tasks import retry_owed_registration_refunds
from tests.test_admin_panel import make_admin_client, verify_id_proof
from tests.test_artists import complete_onboarding_steps, get_artist_profile, make_authenticated_client
from tests.test_customers import seed_payment_statuses

INITIATE = '/artists/registration/payment/initiate/'
SUBMIT = '/artists/onboarding/submit/'
REJECT = '/admin-panel/artists/reject/'
APPROVE = '/admin-panel/artists/approve/'
GATEWAY = 'sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client'


class RegistrationRefundTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {'id': f"order_{data['receipt']}"}
        self.gateway.payment.refund.return_value = {'id': 'rfnd_1'}
        patcher = patch(GATEWAY, return_value=self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client_, self.user = make_authenticated_client(phone_number='+919100007001')
        self.profile = complete_onboarding_steps(self.client_, self.user, pay_fee=False)
        self.admin, _ = make_admin_client(phone_number='+919400000701')

    def _pay_with_gateway(self, promo=None, payment_id='pay_1'):
        resp = self.client_.post(INITIATE, {'promo_code': promo} if promo else {}, format='json')
        payment = ArtistRegistrationPayment.objects.get(gateway_order_id=resp.data['data']['gateway_order_id'])
        self.assertEqual(RegistrationPaymentService.settle(payment.pk, payment_id), 'applied')
        return payment

    def _pay_free(self, code='FREE'):
        PromoCode.objects.get_or_create(code=code, defaults={'discount_percent': 100})
        self.assertEqual(self.client_.post(INITIATE, {'promo_code': code}, format='json').status_code, 201)
        return ArtistRegistrationPayment.objects.get(gateway='promo')

    def _submit_and_reject(self, reason='Photos unclear'):
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        return self.admin.put(REJECT, {'artist_id': self.profile.artist_id, 'reason': reason}, format='json')

    def _fee(self):
        return self.client_.get('/artists/registration/fee/').data['data']

    # --- paid through the gateway
    def test_rejection_refunds_the_fee_through_the_gateway(self):
        payment = self._pay_with_gateway()
        self.assertEqual(self._submit_and_reject().status_code, 200)
        self.gateway.payment.refund.assert_called_once_with('pay_1', {
            'amount': 199900, 'notes': {'registration_payment_id': str(payment.pk)},
        })
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', 'rfnd_1'))
        self.assertIsNotNone(payment.paid_at)                             # kept as the record
        self.assertTrue(Notification.objects.filter(user_id=self.user.user_id, type='refund_initiated').exists())

    def test_a_discounted_payment_refunds_what_was_actually_charged(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        self._pay_with_gateway('HALF')
        self._submit_and_reject()
        self.assertEqual(self.gateway.payment.refund.call_args.args[1]['amount'], 99950)

    def test_after_rejection_the_fee_is_owed_again_but_resubmitting_is_not_blocked(self):
        self._pay_with_gateway()
        self._submit_and_reject()
        fee = self._fee()
        self.assertEqual((fee['paid'], fee['registrationRequired']), (False, True))
        # payment no longer gates submitting, so the artist can resubmit while the fee is unpaid ...
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        self.assertFalse(self.client_.get('/artists/onboarding/status/').data['data']['steps']['registrationFee'])
        # ... and can still pay again (a second payment is allowed because the first was voided)
        self._pay_with_gateway(payment_id='pay_2')
        self.assertEqual(ArtistRegistrationPayment.objects.filter(refund_requested_at__isnull=True, paid_at__isnull=False).count(), 1)
        self.assertTrue(self.client_.get('/artists/onboarding/status/').data['data']['steps']['registrationFee'])

    def test_the_voided_payment_can_no_longer_be_applied(self):
        payment = self._pay_with_gateway()
        self._submit_and_reject()
        self.assertEqual(RegistrationPaymentService.settle(payment.pk, 'pay_1'), 'unapplied')   # a late webhook
        verify = self.client_.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': payment.gateway_order_id, 'razorpay_payment_id': 'pay_1', 'razorpay_signature': 's',
        }, format='json')
        self.assertEqual(verify.status_code, 400)

    def test_rejecting_twice_refunds_once(self):
        self._pay_with_gateway()
        self._submit_and_reject()
        self.admin.put(REJECT, {'artist_id': self.profile.artist_id, 'reason': 'again'}, format='json')
        self.assertEqual(self.gateway.payment.refund.call_count, 1)

    def test_approval_does_not_refund(self):
        self._pay_with_gateway()
        self.client_.post(SUBMIT, {}, format='json')
        verify_id_proof(self.admin, self.profile)
        self.assertEqual(self.admin.put(APPROVE, {'artist_id': self.profile.artist_id}, format='json').status_code, 200)
        self.gateway.payment.refund.assert_not_called()
        self.assertTrue(self._fee()['paid'])

    # --- free registration
    def test_a_free_registration_only_releases_the_promo(self):
        payment = self._pay_free()
        self._submit_and_reject()
        self.gateway.payment.refund.assert_not_called()                   # nothing was ever charged
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', None))
        self.assertEqual(PromoRedemption.objects.get().status, 'released')
        self.assertFalse(Notification.objects.filter(user_id=self.user.user_id, type='refund_initiated').exists())
        self.assertFalse(self._fee()['paid'])

    def test_the_released_promo_can_be_used_again_to_resubmit(self):
        self._pay_free()
        self._submit_and_reject()
        self.assertEqual(self.client_.post(INITIATE, {'promo_code': 'FREE'}, format='json').status_code, 201)
        self.assertTrue(self._fee()['paid'])
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        self.assertEqual(PromoRedemption.objects.filter(status='redeemed').count(), 1)

    def test_an_exempt_artist_has_nothing_to_refund(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        self.assertEqual(self._submit_and_reject().status_code, 200)
        self.gateway.payment.refund.assert_not_called()

    # --- failures and retry
    def test_a_failed_refund_is_recorded_and_the_rejection_still_happens(self):
        payment = self._pay_with_gateway()
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self.assertEqual(self._submit_and_reject().status_code, 200)
        self.assertEqual(get_artist_profile(self.user).approval_status.name, 'rejected')
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id, payment.refund_attempts), ('paid', None, 1))
        self.assertIn('Refund failed', payment.failure_reason)
        self.assertFalse(self._fee()['paid'])                              # the fee no longer counts
        self.assertTrue(Notification.objects.filter(user_id=self.user.user_id, type='refund_pending').exists())

    def test_the_retry_job_finishes_the_refund_once_the_gateway_recovers(self):
        payment = self._pay_with_gateway()
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self._submit_and_reject()
        self.assertEqual(retry_owed_registration_refunds()['waiting'], 1)   # backing off, not retried at once
        ArtistRegistrationPayment.objects.update(refund_last_attempt_at=timezone.now() - timedelta(hours=1))
        self.gateway.payment.refund.side_effect = None
        self.assertEqual(retry_owed_registration_refunds()['refunded'], 1)
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', 'rfnd_1'))
        self.assertEqual(retry_owed_registration_refunds(), {'refunded': 0, 'pending': 0, 'waiting': 0, 'escalated': 0})

    def test_a_refund_that_keeps_failing_is_escalated_to_admins_once(self):
        self._pay_with_gateway()
        self.gateway.payment.refund.side_effect = Exception('gateway down')
        self._submit_and_reject()
        ArtistRegistrationPayment.objects.update(refund_attempts=Configurations.refund_max_attempts)
        self.assertEqual(retry_owed_registration_refunds()['escalated'], 1)
        retry_owed_registration_refunds()
        title = 'Registration refund needs manual attention'
        self.assertEqual(Notification.objects.filter(title=title).count(), 1)

    def test_the_refund_processed_webhook_closes_a_pending_refund(self):
        payment = self._pay_with_gateway()
        self.gateway.payment.refund.side_effect = Exception('lost reply')
        self._submit_and_reject()
        RegistrationPaymentService.record_refund_processed(payment.pk, 'rfnd_hook')
        payment.refresh_from_db()
        self.assertEqual((payment.status.name, payment.gateway_refund_id), ('refunded', 'rfnd_hook'))
        self.assertEqual(retry_owed_registration_refunds()['refunded'], 0)    # nothing left to retry

    def test_the_retry_job_is_scheduled(self):
        from django.conf import settings
        tasks = {entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn('sunndari_apps.payments.tasks.retry_owed_registration_refunds', tasks)
