from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.artists.models import (
    ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption,
)
from sunndari_apps.artists.registration_fee import RegistrationFee
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari.constants import Constants
from tests.test_customers import make_artist, make_customer, seed_payment_statuses

FEE_URL = '/artists/registration/fee/'
PROMO_URL = '/artists/registration/promo/validate/'


class FeeCalculationTest(TestCase):
    """The five examples from the spec, straight from the calculation."""

    def test_the_five_scenarios(self):
        expected = {
            0: ('0.00', '1999.00'),
            25: ('499.75', '1499.25'),
            50: ('999.50', '999.50'),
            75: ('1499.25', '499.75'),
            100: ('1999.00', '0.00'),
        }
        for percent, (discount, payable) in expected.items():
            got = RegistrationFee.calculate(percent)
            self.assertEqual((got['discount'], got['payable']), (Decimal(discount), Decimal(payable)), percent)
            self.assertEqual(got['discount'] + got['payable'], Decimal('1999.00'))

    def test_rounding_is_half_up_to_two_places(self):
        got = RegistrationFee.calculate(Decimal('33.33'))       # 1999 x 0.3333 = 666.2667
        self.assertEqual((got['discount'], got['payable']), (Decimal('666.27'), Decimal('1332.73')))

    def test_the_fee_comes_from_configuration(self):
        with patch('sunndari_apps.artists.registration_fee.Configurations.artist_registration_fee', Decimal('2500')):
            self.assertEqual(RegistrationFee.calculate(50)['payable'], Decimal('1250.00'))


class RegistrationFeeApiTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        self.client_, _, self.profile = make_artist(phone_number='+919100002001')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=False)

    def _promo(self, code='SAVE', percent=50, **extra):
        return PromoCode.objects.create(code=code, discount_percent=percent, **extra)

    def _validate(self, code, client=None, **extra):
        return (client or self.client_).post(PROMO_URL, {'promo_code': code, **extra}, format='json')

    # --- GET fee
    def test_fee_status_for_an_artist_who_has_not_paid(self):
        data = self.client_.get(FEE_URL).data['data']
        self.assertEqual(
            (data['feeAmount'], data['currency'], data['paid'], data['exempt'], data['registrationRequired']),
            ('1999.00', 'INR', False, False, True),
        )

    def test_fee_status_after_payment_and_for_an_exempt_artist(self):
        ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999'), payable_amount=Decimal('1999'),
            status=PaymentStatus.objects.get(name='paid'), paid_at=timezone.now(),
        )
        data = self.client_.get(FEE_URL).data['data']
        self.assertEqual((data['paid'], data['registrationRequired']), (True, False))
        self.assertIsNotNone(data['paidAt'])
        ArtistRegistrationPayment.objects.all().delete()
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        data = self.client_.get(FEE_URL).data['data']
        self.assertEqual((data['exempt'], data['registrationRequired']), (True, False))

    def test_fee_status_needs_login_and_an_artist_account(self):
        self.assertEqual(APIClient().get(FEE_URL).status_code, 401)
        customer, _ = make_customer(phone_number='+919100002002')
        self.assertEqual(customer.get(FEE_URL).status_code, 400)

    # --- promo validate
    def test_each_discount_level_returns_the_right_amounts(self):
        for percent, discount, payable, requires in (
            (25, '499.75', '1499.25', True), (50, '999.50', '999.50', True),
            (75, '1499.25', '499.75', True), (100, '1999.00', '0.00', False),
        ):
            self._promo(code=f'CODE{percent}', percent=percent)
            data = self._validate(f'CODE{percent}').data['data']
            self.assertEqual(
                (data['feeAmount'], data['discountPercent'], data['discountAmount'], data['payableAmount'], data['requiresPayment']),
                ('1999.00', f'{percent}.00', discount, payable, requires), percent,
            )

    def test_codes_match_regardless_of_case_and_spaces(self):
        self._promo(code='Welcome')
        resp = self._validate('  welcome ')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['promoCode'], 'WELCOME')

    def test_validating_records_nothing(self):
        self._promo()
        self._validate('SAVE')
        self.assertEqual(PromoRedemption.objects.count(), 0)
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)

    def test_amounts_sent_by_the_client_are_ignored(self):
        self._promo(percent=25)
        data = self._validate('SAVE', discount_percent=100, payable_amount='0', fee_amount='1').data['data']
        self.assertEqual((data['discountPercent'], data['payableAmount']), ('25.00', '1499.25'))

    def test_unknown_inactive_expired_and_not_yet_valid_codes_are_refused(self):
        now = timezone.now()
        self._promo(code='OFF', is_active=False)
        self._promo(code='OLD', valid_until=now - timedelta(days=1))
        self._promo(code='SOON', valid_from=now + timedelta(days=1))
        for code, message in (
            ('NOPE', Constants.promo_invalid), ('OFF', Constants.promo_invalid),
            ('OLD', Constants.promo_expired), ('SOON', Constants.promo_expired),
        ):
            resp = self._validate(code)
            self.assertEqual(resp.status_code, 400, code)
            self.assertIn(message, resp.data['message'])

    def test_a_code_inside_its_validity_window_works(self):
        now = timezone.now()
        self._promo(valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1))
        self.assertEqual(self._validate('SAVE').status_code, 200)

    def test_a_code_the_artist_already_uses_is_refused_but_a_released_one_is_not(self):
        promo = self._promo()
        payment = ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999'), payable_amount=Decimal('999.50'),
            status=PaymentStatus.objects.get(name='pending'), promo=promo,
        )
        redemption = PromoRedemption.objects.create(promo=promo, artist=self.profile, registration_payment=payment)
        resp = self._validate('SAVE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.promo_already_used, resp.data['message'])
        PromoRedemption.objects.filter(pk=redemption.pk).update(status='released')
        self.assertEqual(self._validate('SAVE').status_code, 200)

    def test_the_overall_limit_counts_other_artists(self):
        promo = self._promo(max_redemptions=1)
        _, _, other = make_artist(phone_number='+919100002003')
        payment = ArtistRegistrationPayment.objects.create(
            artist=other, fee_amount=Decimal('1999'), payable_amount=Decimal('999.50'),
            status=PaymentStatus.objects.get(name='pending'), promo=promo,
        )
        PromoRedemption.objects.create(promo=promo, artist=other, registration_payment=payment, status='redeemed')
        resp = self._validate('SAVE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.promo_fully_redeemed, resp.data['message'])

    def test_exempt_and_already_paid_artists_cannot_use_a_promo(self):
        self._promo()
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=True)
        resp = self._validate('SAVE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.registration_fee_not_required, resp.data['message'])

    def test_a_discount_that_leaves_less_than_the_gateway_minimum_is_refused(self):
        self._promo(code='ALMOST', percent=Decimal('99.99'))        # leaves 0.20
        resp = self._validate('ALMOST')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.promo_not_applicable, resp.data['message'])

    def test_validate_needs_login_a_code_and_an_artist_account(self):
        self.assertEqual(APIClient().post(PROMO_URL, {'promo_code': 'X'}, format='json').status_code, 401)
        self.assertEqual(self.client_.post(PROMO_URL, {}, format='json').status_code, 400)
        customer, _ = make_customer(phone_number='+919100002004')
        self._promo()
        self.assertEqual(self._validate('SAVE', client=customer).status_code, 400)
