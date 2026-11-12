"""Step 1 of the booking-accepting rules: approval, registration payment, bookings ON and customer visibility
are four separate facts, combined only by ArtistProfile.public_filter() at read time."""
import importlib
from decimal import Decimal

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment, PricingPackage
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from tests.test_artists import make_package, make_sub_category
from tests.test_customers import make_artist, make_user, seed_payment_statuses


class AcceptingEligibilityTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.pending_status = PaymentStatus.objects.get(name='pending')
        self._n = 0

    def _artist(self, approved=True, exempt=False, accepting=True, paid=False, voided=False):
        self._n += 1
        _, _, profile = make_artist(phone_number=f'+9199000070{self._n:02d}', approved=approved)
        profile.registration_fee_exempt = exempt
        profile.is_accepting_bookings = accepting
        profile.save()
        if paid or voided:
            ArtistRegistrationPayment.objects.create(
                artist=profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
                status=self.pending_status, paid_at=timezone.now(),
                refund_requested_at=timezone.now() if voided else None,
            )
        return profile

    def _public_ids(self):
        return set(ArtistProfile.objects.filter(ArtistProfile.public_filter()).values_list('artist_id', flat=True))

    # --- a newly registered artist
    def test_a_newly_registered_artist_starts_with_bookings_off(self):
        user = make_user('+919900007999', 'artist', 'New Artist')
        ArtistProfile.create_for_user(user_id=user.user_id)
        profile = ArtistProfile.objects.get(user_id=user.user_id)
        self.assertFalse(profile.is_accepting_bookings)
        self.assertFalse(profile.accepting_locked_by_admin)

    # --- eligibility is computed from the payment, not stored
    def test_eligibility_needs_exemption_or_a_completed_payment(self):
        self.assertFalse(ArtistProfile.is_eligible(self._artist().artist_id))
        self.assertTrue(ArtistProfile.is_eligible(self._artist(exempt=True).artist_id))
        self.assertTrue(ArtistProfile.is_eligible(self._artist(paid=True).artist_id))

    def test_a_payment_that_was_only_started_does_not_make_an_artist_eligible(self):
        profile = self._artist()
        ArtistRegistrationPayment.objects.create(
            artist=profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=self.pending_status, gateway_order_id='order_started',
        )
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        self.assertNotIn(profile.artist_id, self._public_ids())

    def test_a_refunded_or_voided_payment_removes_eligibility(self):
        profile = self._artist(voided=True)
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        self.assertNotIn(profile.artist_id, self._public_ids())

    # --- the visibility matrix
    def test_only_approved_paid_and_accepting_artists_are_public(self):
        visible_paid = self._artist(paid=True)
        visible_exempt = self._artist(exempt=True)
        approved_unpaid = self._artist()
        approved_paid_off = self._artist(paid=True, accepting=False)
        paid_unapproved = self._artist(approved=False, paid=True)
        refunded = self._artist(voided=True)
        self.assertEqual(self._public_ids(), {visible_paid.artist_id, visible_exempt.artist_id})
        for hidden in (approved_unpaid, approved_paid_off, paid_unapproved, refunded):
            self.assertNotIn(hidden.artist_id, self._public_ids())

    def test_a_rejected_artist_who_paid_is_hidden(self):
        profile = self._artist(approved=False, paid=True)
        profile.approval_status = ApprovalStatus.objects.get(name='rejected')
        profile.save()
        self.assertNotIn(profile.artist_id, self._public_ids())

    def test_paying_does_not_switch_bookings_on(self):
        profile = self._artist(accepting=False)
        ArtistRegistrationPayment.objects.create(
            artist=profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=self.pending_status, paid_at=timezone.now(),
        )
        profile.refresh_from_db()
        self.assertFalse(profile.is_accepting_bookings)
        self.assertTrue(ArtistProfile.is_eligible(profile.artist_id))
        self.assertNotIn(profile.artist_id, self._public_ids())

    # --- the same filter works from a model that reaches the artist through a foreign key
    def test_the_filter_works_through_the_artist_foreign_key(self):
        visible = self._artist(paid=True)
        hidden = self._artist()
        sub_category = make_sub_category()
        make_package(visible, sub_category=sub_category)
        make_package(hidden, sub_category=sub_category, name='Other Package')
        ids = set(PricingPackage.objects.filter(ArtistProfile.public_filter('artist__')).values_list('artist_id', flat=True))
        self.assertEqual(ids, {visible.artist_id})

    # --- the migration's data step
    def test_the_migration_switches_off_only_ineligible_artists(self):
        migration = importlib.import_module('sunndari_apps.artists.migrations.0022_accepting_bookings_gating')
        exempt = self._artist(exempt=True)
        paid = self._artist(paid=True)
        unpaid = self._artist()
        voided = self._artist(voided=True)
        migration.switch_off_ineligible(apps, None)
        for artist in (exempt, paid, unpaid, voided):
            artist.refresh_from_db()
        self.assertTrue(exempt.is_accepting_bookings)
        self.assertTrue(paid.is_accepting_bookings)
        self.assertFalse(unpaid.is_accepting_bookings)
        self.assertFalse(voided.is_accepting_bookings)
