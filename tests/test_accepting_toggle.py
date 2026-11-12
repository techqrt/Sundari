"""The artist's own Booking Accepting switch (PUT /artists/profile/accepting_bookings/). OFF is always allowed; ON
needs an approved artist who has settled the registration fee (or is exempt) and has not been switched off by an
admin. Checked on the backend, so a direct API call cannot get around it."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from tests.test_customers import make_artist, seed_payment_statuses

URL = '/artists/profile/accepting_bookings/'


class AcceptingToggleTest(TestCase):

    def setUp(self):
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.n = 0

    def _artist(self, approval='approved', exempt=False, paid=False, voided=False, locked=False, accepting=False):
        self.n += 1
        client, _, profile = make_artist(phone_number=f'+9199000080{self.n:02d}', approved=False)
        profile.approval_status = ApprovalStatus.objects.get(name=approval)
        profile.registration_fee_exempt = exempt
        profile.accepting_locked_by_admin = locked
        profile.is_accepting_bookings = accepting
        profile.save()
        if paid or voided:
            self._payment(profile, paid_at=timezone.now(), voided=voided)
        return client, profile

    def _payment(self, profile, paid_at=None, voided=False, status='pending', order=None):
        return ArtistRegistrationPayment.objects.create(
            artist=profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=PaymentStatus.objects.get(name=status), paid_at=paid_at, gateway_order_id=order,
            refund_requested_at=timezone.now() if voided else None,
        )

    def _set(self, client, on):
        return client.put(URL, {'is_accepting_bookings': on}, format='json')

    def _flag(self, profile):
        return ArtistProfile.objects.get(artist_id=profile.artist_id).is_accepting_bookings

    def _refused(self, client, profile, message):
        resp = self._set(client, True)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(message, resp.data['message'])
        self.assertFalse(self._flag(profile))

    # --- turning ON
    def test_a_paid_approved_artist_can_turn_bookings_on(self):
        client, profile = self._artist(paid=True)
        resp = self._set(client, True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['isAcceptingBookings'])
        self.assertTrue(self._flag(profile))

    def test_an_exempt_approved_artist_can_turn_bookings_on(self):
        client, profile = self._artist(exempt=True)
        self.assertEqual(self._set(client, True).status_code, 200)
        self.assertTrue(self._flag(profile))

    def test_a_free_registration_with_a_full_promo_makes_the_artist_eligible(self):
        client, profile = self._artist()
        from sunndari_apps.artists.models import PromoCode
        PromoCode.objects.create(code='FREE', discount_percent=100)
        self.assertEqual(client.post('/artists/registration/payment/initiate/', {'promo_code': 'FREE'}, format='json').status_code, 201)
        self.assertEqual(self._set(client, True).status_code, 200)

    def test_an_unpaid_artist_cannot_turn_bookings_on(self):
        client, profile = self._artist()
        self._refused(client, profile, Constants.accepting_requires_payment)

    def test_a_payment_that_was_only_started_is_not_enough(self):
        client, profile = self._artist()
        self._payment(profile, order='order_started')
        self._refused(client, profile, Constants.accepting_requires_payment)

    def test_a_failed_payment_is_not_enough(self):
        client, profile = self._artist()
        self._payment(profile, status='failed', order='order_failed')
        self._refused(client, profile, Constants.accepting_requires_payment)

    def test_a_refunded_payment_is_not_enough(self):
        client, profile = self._artist(voided=True)
        self._refused(client, profile, Constants.accepting_requires_payment)

    def test_an_artist_who_is_not_approved_cannot_turn_bookings_on_even_if_paid(self):
        for approval in ('pending', 'rejected'):
            client, profile = self._artist(approval=approval, paid=True)
            self._refused(client, profile, Constants.accepting_requires_approval)

    def test_a_suspended_artist_cannot_turn_bookings_on(self):
        client, profile = self._artist(approval='suspended', paid=True)
        self._refused(client, profile, Constants.artist_suspended)

    def test_an_artist_cannot_undo_an_admin_off(self):
        client, profile = self._artist(paid=True, locked=True)
        self._refused(client, profile, Constants.accepting_locked_by_admin)
        self.assertTrue(ArtistProfile.objects.get(artist_id=profile.artist_id).accepting_locked_by_admin)

    def test_paying_alone_does_not_turn_bookings_on(self):
        client, profile = self._artist(paid=True)
        self.assertFalse(self._flag(profile))                       # eligible, but still OFF until the artist chooses

    # --- turning OFF
    def test_an_artist_can_always_turn_bookings_off(self):
        cases = {
            'paid': dict(paid=True, accepting=True),
            'unpaid': dict(accepting=True),
            'pending': dict(approval='pending', accepting=True),
            'suspended': dict(approval='suspended', accepting=True),
            'locked': dict(locked=True, accepting=True),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                client, profile = self._artist(**kwargs)
                resp = self._set(client, False)
                self.assertEqual(resp.status_code, 200)
                self.assertFalse(self._flag(profile))

    def test_the_artists_own_off_does_not_lock_them_out(self):
        client, profile = self._artist(paid=True, accepting=True)
        self._set(client, False)
        self.assertFalse(ArtistProfile.objects.get(artist_id=profile.artist_id).accepting_locked_by_admin)
        self.assertEqual(self._set(client, True).status_code, 200)   # they can switch back on themselves

    def test_a_repeat_request_changes_nothing(self):
        client, profile = self._artist(paid=True, accepting=True)
        self.assertEqual(self._set(client, True).status_code, 200)
        self.assertTrue(self._flag(profile))

    # --- who may call it
    def test_a_customer_cannot_use_it(self):
        from tests.test_customers import make_customer
        customer, _ = make_customer(phone_number='+919900008999')
        self.assertEqual(self._set(customer, True).status_code, 400)

    def test_an_artist_only_changes_their_own_switch(self):
        mine, my_profile = self._artist(paid=True)
        _, other = self._artist(paid=True)
        self._set(mine, True)
        self.assertTrue(self._flag(my_profile))
        self.assertFalse(self._flag(other))
