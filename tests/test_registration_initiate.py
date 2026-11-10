from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import razorpay
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.constants import Constants
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption,
)
from tests.test_customers import make_artist, make_customer, seed_payment_statuses

URL = '/artists/registration/payment/initiate/'
GATEWAY = 'sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client'


class InitiateRegistrationPaymentTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        self.client_, _, self.profile = make_artist(phone_number='+919100003001')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=False)
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        patcher = patch(GATEWAY, return_value=self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _promo(self, code='SAVE', percent=50, **extra):
        return PromoCode.objects.create(code=code, discount_percent=percent, **extra)

    def _initiate(self, promo_code=None, client=None, **extra):
        body = {**extra}
        if promo_code is not None:
            body['promo_code'] = promo_code
        return (client or self.client_).post(URL, body, format='json')

    # --- amounts
    def test_no_promo_charges_the_full_fee(self):
        resp = self._initiate()
        self.assertEqual(resp.status_code, 201, resp.data)
        data = resp.data['data']
        self.assertEqual((data['amount'], data['currency'], data['payable_amount'], data['fully_covered_by_promo']),
                         (199900, 'INR', '1999.00', False))
        self.assertTrue(data['gateway_order_id'].startswith('order_registration_'))
        payment = ArtistRegistrationPayment.objects.get()
        self.assertEqual((payment.status.name, payment.gateway, payment.paid_at), ('pending', 'razorpay', None))
        self.assertEqual(payment.gateway_order_id, data['gateway_order_id'])

    def test_each_partial_discount_orders_exactly_the_payable_amount(self):
        for percent, paise in ((25, 149925), (50, 99950), (75, 49975)):
            ArtistRegistrationPayment.objects.all().delete()
            self._promo(code=f'P{percent}', percent=percent)
            resp = self._initiate(f'P{percent}')
            self.assertEqual(resp.status_code, 201, resp.data)
            self.assertEqual(resp.data['data']['amount'], paise, percent)
            self.assertEqual(self.gateway.order.create.call_args.kwargs['data']['amount'], paise)
            redemption = PromoRedemption.objects.get(registration_payment__artist=self.profile, promo__code=f'P{percent}')
            self.assertEqual(redemption.status, 'reserved')              # reserved until the money arrives
            PromoRedemption.objects.all().delete()

    def test_amounts_sent_by_the_client_are_ignored(self):
        self._promo(percent=25)
        resp = self._initiate('SAVE', amount=1, payable_amount='1', discount_percent=100, fee_amount='1')
        self.assertEqual(resp.data['data']['amount'], 149925)

    # --- 100%
    def test_a_100_percent_code_completes_without_the_gateway(self):
        self._promo(code='FREE', percent=100)
        resp = self._initiate('FREE')
        self.assertEqual(resp.status_code, 201, resp.data)
        data = resp.data['data']
        self.assertEqual((data['fully_covered_by_promo'], data['amount'], data['gateway_order_id'], data['payable_amount']),
                         (True, 0, None, '0.00'))
        self.gateway.order.create.assert_not_called()
        payment = ArtistRegistrationPayment.objects.get()
        self.assertEqual((payment.status.name, payment.gateway, payment.discount_amount), ('paid', 'promo', Decimal('1999.00')))
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(PromoRedemption.objects.get().status, 'redeemed')
        fee = self.client_.get('/artists/registration/fee/').data['data']
        self.assertEqual((fee['paid'], fee['registrationRequired']), (True, False))

    def test_a_second_attempt_after_completion_is_refused(self):
        self._promo(code='FREE', percent=100)
        self._initiate('FREE')
        resp = self._initiate('FREE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_fee_not_required, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 1)

    # --- duplicates
    def test_a_repeat_tap_reuses_the_open_order(self):
        first = self._initiate()
        second = self._initiate()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data['data']['gateway_order_id'], second.data['data']['gateway_order_id'])
        self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 1)

    def test_a_repeat_tap_with_the_same_promo_reuses_it_in_any_letter_case(self):
        self._promo()
        self._initiate('SAVE')
        resp = self._initiate('save')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.gateway.order.create.call_count, 1)
        self.assertEqual(PromoRedemption.objects.count(), 1)

    def test_changing_the_promo_replaces_the_open_attempt_and_frees_the_old_code(self):
        self._promo(code='HALF', percent=50)
        self._promo(code='QUARTER', percent=25)
        self._initiate('HALF')
        resp = self._initiate('QUARTER')
        self.assertEqual((resp.status_code, resp.data['data']['amount']), (201, 149925))
        old = ArtistRegistrationPayment.objects.get(promo__code='HALF')
        self.assertEqual(old.status.name, 'failed')
        self.assertEqual(PromoRedemption.objects.get(promo__code='HALF').status, 'released')
        self.assertEqual(PromoRedemption.objects.get(promo__code='QUARTER').status, 'reserved')
        # and the artist can go back to the first code
        self.assertEqual(self._initiate('HALF').status_code, 201)

    def test_removing_the_promo_replaces_the_attempt_with_the_full_fee(self):
        self._promo()
        self._initiate('SAVE')
        resp = self._initiate()
        self.assertEqual((resp.status_code, resp.data['data']['amount']), (201, 199900))
        self.assertEqual(PromoRedemption.objects.get().status, 'released')

    def test_an_abandoned_attempt_does_not_keep_its_promo_locked(self):
        self._promo()
        self._initiate('SAVE')
        ArtistRegistrationPayment.objects.update(created_at=timezone.now() - timedelta(hours=2))
        resp = self._initiate('SAVE')
        self.assertEqual((resp.status_code, resp.data['data']['amount']), (201, 99950))
        self.assertEqual(self.gateway.order.create.call_count, 2)
        self.assertEqual(PromoRedemption.objects.filter(status='released').count(), 1)

    # --- refusals
    def test_an_invalid_promo_creates_nothing(self):
        resp = self._initiate('NOPE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.promo_invalid, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)
        self.gateway.order.create.assert_not_called()

    def test_expired_used_up_and_already_used_codes_are_refused(self):
        self._promo(code='OLD', valid_until=timezone.now() - timedelta(days=1))
        self._promo(code='ONE', max_redemptions=1)
        other_client, _, other = make_artist(phone_number='+919100003002')
        ArtistProfile.objects.filter(artist_id=other.artist_id).update(registration_fee_exempt=False)
        self.assertEqual(self._initiate('ONE', client=other_client).status_code, 201)
        for code, message in (('OLD', Constants.promo_expired), ('ONE', Constants.promo_fully_redeemed)):
            resp = self._initiate(code)
            self.assertEqual(resp.status_code, 400, code)
            self.assertIn(message, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.filter(artist=self.profile).count(), 0)

    def test_an_exempt_artist_cannot_start_a_payment(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        resp = self._initiate()
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_fee_not_required, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)

    def test_requires_login_and_an_artist_account(self):
        self.assertEqual(APIClient().post(URL, {}, format='json').status_code, 401)
        customer, _ = make_customer(phone_number='+919100003003')
        self.assertEqual(self._initiate(client=customer).status_code, 400)

    # --- gateway failure
    def test_a_gateway_failure_fails_the_attempt_and_frees_the_promo(self):
        self._promo()
        self.gateway.order.create.side_effect = razorpay.errors.ServerError('down')
        resp = self._initiate('SAVE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_gateway_unavailable, resp.data['message'])
        self.assertEqual(ArtistRegistrationPayment.objects.get().status.name, 'failed')
        self.assertEqual(PromoRedemption.objects.get().status, 'released')
        # a retry once the gateway is back works, with the same code
        self.gateway.order.create.side_effect = lambda data: {'id': 'order_retry'}
        self.assertEqual(self._initiate('SAVE').status_code, 201)
        self.assertEqual(ArtistRegistrationPayment.objects.filter(status__name='pending').count(), 1)

    def test_starting_a_payment_does_not_make_the_artist_paid(self):
        self._initiate()
        fee = self.client_.get('/artists/registration/fee/').data['data']
        self.assertEqual((fee['paid'], fee['registrationRequired']), (False, True))
        self.assertIsNone(ArtistRegistrationPayment.objects.get().paid_at)
