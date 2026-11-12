from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from sunndari.config import Configurations
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption,
)
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from tests.test_customers import make_artist, seed_payment_statuses


class RegistrationModelsTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        # Pending artists: the tests here are about the exemption, which a live fixture artist already has.
        _, _, self.profile = make_artist(phone_number='+919100001001', approved=False)
        _, _, self.other = make_artist(phone_number='+919100001002', approved=False)
        self.pending = PaymentStatus.objects.get(name='pending')

    def _payment(self, artist, paid=False, promo=None):
        return ArtistRegistrationPayment.objects.create(
            artist=artist, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=self.pending, promo=promo, paid_at=timezone.now() if paid else None,
        )

    def test_fee_is_1999_and_decimal(self):
        self.assertEqual(Configurations.artist_registration_fee, Decimal('1999.00'))

    def test_fee_can_be_changed_from_the_environment(self):
        import os
        import subprocess
        import sys
        code = 'from sunndari.config import Configurations as C; print(C.artist_registration_fee)'
        for value, expected in (('2500.50', '2500.50'), (None, '1999.00')):
            env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'sunndari.settings'}
            env.pop('ARTIST_REGISTRATION_FEE', None)
            if value:
                env['ARTIST_REGISTRATION_FEE'] = value
            out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env)
            self.assertEqual(out.stdout.strip().splitlines()[-1], expected, out.stderr)

    def test_a_new_artist_is_not_exempt(self):
        self.assertFalse(ArtistProfile.objects.get(artist_id=self.profile.artist_id).registration_fee_exempt)

    def test_promo_codes_are_stored_upper_case_and_unique_ignoring_case(self):
        promo = PromoCode.objects.create(code=' welcome50 ', discount_percent=50)
        self.assertEqual(promo.code, 'WELCOME50')
        with self.assertRaises(IntegrityError), transaction.atomic():
            PromoCode.objects.create(code='Welcome50', discount_percent=25)

    def test_an_artist_can_have_only_one_completed_registration_payment(self):
        self._payment(self.profile, paid=True)
        self._payment(self.profile, paid=False)           # an open or failed attempt is fine
        self._payment(self.other, paid=True)               # another artist is unaffected
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._payment(self.profile, paid=True)

    def test_a_promo_can_be_used_once_per_artist_but_again_after_release(self):
        promo = PromoCode.objects.create(code='HALF', discount_percent=50)
        first = PromoRedemption.objects.create(
            promo=promo, artist=self.profile, registration_payment=self._payment(self.profile, promo=promo),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PromoRedemption.objects.create(
                promo=promo, artist=self.profile, registration_payment=self._payment(self.profile, promo=promo),
            )
        PromoRedemption.objects.filter(pk=first.pk).update(status='released')
        PromoRedemption.objects.create(
            promo=promo, artist=self.profile, registration_payment=self._payment(self.profile, promo=promo),
        )
        PromoRedemption.objects.create(      # a different artist may use the same code
            promo=promo, artist=self.other, registration_payment=self._payment(self.other, promo=promo),
        )

    def test_the_data_migration_exempts_only_approved_artists(self):
        import importlib
        from django.apps import apps
        approved = ApprovalStatus.objects.get_or_create(name='approved')[0]
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(approval_status=approved)
        ArtistProfile.objects.filter(artist_id=self.other.artist_id).update(
            approval_status=ApprovalStatus.objects.get_or_create(name='pending')[0],
        )
        migration = importlib.import_module('sunndari_apps.artists.migrations.0019_exempt_already_approved_artists')
        migration.exempt_approved(apps, None)
        self.assertTrue(ArtistProfile.objects.get(artist_id=self.profile.artist_id).registration_fee_exempt)
        self.assertFalse(ArtistProfile.objects.get(artist_id=self.other.artist_id).registration_fee_exempt)
