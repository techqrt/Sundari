"""The registration fee is an onboarding step: an artist who has not paid (and is not exempt) cannot submit for
review, and an admin cannot approve them. The admin approval workflow is otherwise unchanged."""
from unittest.mock import patch

from django.test import TestCase

from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment, PromoCode
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari.constants import Constants
from tests.test_admin_panel import make_admin_client, verify_id_proof
from tests.test_artists import complete_onboarding_steps, get_artist_profile, make_authenticated_client
from tests.test_customers import seed_payment_statuses

STATUS = '/artists/onboarding/status/'
SUBMIT = '/artists/onboarding/submit/'
APPROVE = '/admin-panel/artists/approve/'
DETAIL = '/admin-panel/artists/review/get/'


class RegistrationFeeGatingTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.client_, self.user = make_authenticated_client(phone_number='+919100006001')
        self.profile = complete_onboarding_steps(self.client_, self.user, pay_fee=False)

    def _steps(self):
        return self.client_.get(STATUS).data['data']['steps']

    def _pay_with_free_code(self):
        PromoCode.objects.get_or_create(code='FREE', defaults={'discount_percent': 100})
        return self.client_.post('/artists/registration/payment/initiate/', {'promo_code': 'FREE'}, format='json')

    # --- onboarding step and submit
    def test_the_status_shows_the_fee_step_unfinished(self):
        steps = self._steps()
        self.assertFalse(steps['registrationFee'])
        self.assertTrue(all(done for name, done in steps.items() if name != 'registrationFee'))

    def test_an_unpaid_artist_cannot_submit_even_with_every_other_step_done(self):
        resp = self.client_.post(SUBMIT, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Incomplete: Registration fee payment', str(resp.data))
        self.assertIsNone(get_artist_profile(self.user).submitted_for_review_at)

    def test_starting_a_payment_is_not_enough_to_submit(self):
        PromoCode.objects.create(code='HALF', discount_percent=50)
        with patch('sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client') as client:
            client.return_value.order.create.return_value = {'id': 'order_open'}
            self.client_.post('/artists/registration/payment/initiate/', {'promo_code': 'HALF'}, format='json')
        self.assertFalse(self._steps()['registrationFee'])
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 400)

    def test_after_the_fee_is_paid_the_artist_can_submit(self):
        self.assertEqual(self._pay_with_free_code().status_code, 201)
        self.assertTrue(self._steps()['registrationFee'])
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        self.assertEqual(self.client_.get(STATUS).data['data']['status'], 'submitted')

    def test_an_exempt_artist_can_submit_without_paying(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        self.assertTrue(self._steps()['registrationFee'])
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)

    # --- admin
    def _submitted_artist(self):
        self._pay_with_free_code()
        self.assertEqual(self.client_.post(SUBMIT, {}, format='json').status_code, 200)
        admin, _ = make_admin_client(phone_number='+919400000601')
        verify_id_proof(admin, self.profile)
        return admin

    def test_admin_cannot_approve_an_artist_who_has_not_paid(self):
        admin = self._submitted_artist()
        ArtistRegistrationPayment.objects.all().delete()            # e.g. a record removed or never settled
        resp = admin.put(APPROVE, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_fee_unpaid, resp.data['message'])
        self.assertNotEqual(get_artist_profile(self.user).approval_status.name, 'approved')

    def test_admin_approves_a_paid_artist_as_before(self):
        admin = self._submitted_artist()
        resp = admin.put(APPROVE, {'artist_id': self.profile.artist_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(get_artist_profile(self.user).approval_status.name, 'approved')

    def test_admin_approves_an_exempt_artist_without_a_payment(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        self.client_.post(SUBMIT, {}, format='json')
        admin, _ = make_admin_client(phone_number='+919400000602')
        verify_id_proof(admin, self.profile)
        self.assertEqual(admin.put(APPROVE, {'artist_id': self.profile.artist_id}, format='json').status_code, 200)

    def test_paying_does_not_approve_the_artist(self):
        self._pay_with_free_code()
        self.assertEqual(get_artist_profile(self.user).approval_status.name, 'pending')
        self.client_.post(SUBMIT, {}, format='json')
        self.assertEqual(get_artist_profile(self.user).approval_status.name, 'pending')    # still waits for admin

    def test_the_review_detail_shows_the_fee_status_to_the_admin(self):
        admin = self._submitted_artist()
        data = admin.get(DETAIL, {'artist_id': self.profile.artist_id}).data['data']
        self.assertEqual((data['registrationFeePaid'], data['registrationFeeExempt']), (True, False))
