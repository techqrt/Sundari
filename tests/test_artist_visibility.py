"""Customer-facing visibility of an artist: approved by an admin AND registration payment settled (or exempt) AND
bookings switched ON. The four facts (approval, payment, bookings switch, visibility) are separate; visibility is
only ever worked out from the other three, at read time, in ArtistProfile.public_filter().

Every path that shows one artist to someone else is checked in every state, so a direct call cannot get around the
rule: search, service lists, artist detail, availability, booking creation, the shared public page, and the
artist's own endpoints when asked for someone else's data."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from tests.booking_address import address_for
from tests.test_admin_panel import make_admin_client
from tests.test_customers import (
    make_artist, make_customer, make_location_preference, make_location_type, make_package, make_schedule,
    make_sub_category, next_weekday, seed_booking_statuses, seed_payment_statuses,
)

# (approval, bookings ON, fee exempt, has a completed payment, payment refunded/voided)
VISIBLE = {
    'approved + exempt + ON': ('approved', True, True, False, False),
    'approved + paid + ON': ('approved', True, False, True, False),
}
HIDDEN = {
    'approved + unpaid + ON': ('approved', True, False, False, False),
    'approved + paid + OFF': ('approved', False, False, True, False),
    'approved + exempt + OFF': ('approved', False, True, False, False),
    'approved + refunded + ON': ('approved', True, False, False, True),
    'pending + paid + ON': ('pending', True, False, True, False),
    'rejected + paid + ON': ('rejected', True, False, True, False),
    'suspended + paid + ON': ('suspended', True, False, True, False),
}


class ArtistVisibilityTest(TestCase):

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.sub = make_sub_category(name='Subject Bridal')
        self.location = make_location_type('Studio')
        self.date = next_weekday(2)

        self.owner, self.user, self.profile = make_artist(phone_number='+919900010001', approved=False)
        self.package = make_package(self.profile, sub_category=self.sub, price=1500, name='Subject Package')
        make_location_preference(self.profile, self.location)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        self.slug = ArtistProfile.ensure_public_slug(self.user.user_id)

        # A control artist who is always live: the rule must hide the subject without hiding everyone.
        _, _, self.control = make_artist(phone_number='+919900010002', name='Control Artist')
        self.control_sub = make_sub_category(name='Control Bridal')
        make_package(self.control, sub_category=self.control_sub, price=1000, name='Control Package')

        self.customer, _ = make_customer(phone_number='+919900010003')
        self.other_artist, _, _ = make_artist(phone_number='+919900010004', name='Other Artist')
        self.hour = 9

    # --- helpers
    def _state(self, approval, accepting, exempt, paid, voided):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(
            approval_status=ApprovalStatus.objects.get(name=approval),
            is_accepting_bookings=accepting, registration_fee_exempt=exempt,
        )
        ArtistRegistrationPayment.objects.filter(artist=self.profile).delete()
        if paid or voided:
            ArtistRegistrationPayment.objects.create(
                artist=self.profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
                status=PaymentStatus.objects.get(name='paid'), paid_at=timezone.now(),
                refund_requested_at=timezone.now() if voided else None,
            )

    def _seen_by(self, client):
        """Which paths show the subject artist to this viewer."""
        artist_id = self.profile.artist_id
        ok = lambda resp: resp.status_code == 200
        get = lambda url, **query: client.get(url, {'artist_id': artist_id, **query})
        search = client.get('/customers/artists/search/').data['data']['data']
        services = client.get('/core/service-sub-category/get_all/').data['data']['data']
        self.hour += 1
        booking = client.post('/customers/bookings/create/', {
            **address_for(client), 'artist_id': artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': f'{self.hour:02d}:00:00',
        }, format='json')
        return {
            'search': any(row['artistId'] == artist_id for row in search),
            'bookable service': any(row['name'] == 'Subject Bridal' for row in services),
            'detail': ok(get('/customers/artists/get/')),
            'availability': ok(get('/customers/artists/availability/', booking_date=self.date.strftime('%d-%m-%y'))),
            'create booking': booking.status_code == 201,
            'public page': ok(APIClient().get('/public/artists/get/', {'slug': self.slug})),
            'profile': ok(get('/artists/profile/get/')),
            'packages': ok(get('/artists/packages/get_all/')),
            'portfolio': ok(get('/artists/portfolio/get_all/')),
            'add-ons': ok(get('/artists/addons/get_all/')),
            'service areas': ok(get('/artists/service_areas/get_all/')),
            'services': ok(get('/artists/services/get_all/')),
            'locations': ok(get('/artists/locations/get_all/')),
            'specialities': ok(get('/artists/profile/specialities/get_all/')),
        }

    # --- the rule, on every path
    def test_a_customer_sees_the_artist_everywhere_only_when_all_three_conditions_hold(self):
        for name, state in VISIBLE.items():
            with self.subTest(name):
                self._state(*state)
                seen = self._seen_by(self.customer)
                self.assertTrue(all(seen.values()), f'{name}: {seen}')
        for name, state in HIDDEN.items():
            with self.subTest(name):
                self._state(*state)
                seen = self._seen_by(self.customer)
                self.assertFalse(any(seen.values()), f'{name}: {seen}')

    def test_another_artist_is_held_to_the_same_rule_when_looking_at_someone_else(self):
        for name, state in HIDDEN.items():
            with self.subTest(name):
                self._state(*state)
                seen = self._seen_by(self.other_artist)
                for path in ('profile', 'packages', 'portfolio', 'add-ons', 'service areas', 'services', 'locations', 'specialities'):
                    self.assertFalse(seen[path], f'{name}: {path} leaked to another artist')

    def test_the_control_artist_stays_visible_whatever_state_the_subject_is_in(self):
        for name, state in {**VISIBLE, **HIDDEN}.items():
            with self.subTest(name):
                self._state(*state)
                search = self.customer.get('/customers/artists/search/').data['data']['data']
                self.assertIn(self.control.artist_id, [row['artistId'] for row in search])
                detail = self.customer.get('/customers/artists/get/', {'artist_id': self.control.artist_id})
                self.assertEqual(detail.status_code, 200)

    def test_an_admin_lock_wins_even_if_the_stored_flag_says_on(self):
        """Normally a lock implies OFF. If the two ever disagree (a race, a stray edit) the admin's decision still
        hides the artist and blocks bookings, on every path."""
        self._state(*VISIBLE['approved + paid + ON'])
        self.assertTrue(all(v for v in self._seen_by(self.customer).values()))
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(accepting_locked_by_admin=True)
        seen = self._seen_by(self.customer)
        self.assertFalse(any(seen.values()), seen)
        self.assertFalse(ArtistProfile.is_public(self.profile.artist_id))

    def test_a_hidden_artist_is_the_same_not_found_as_one_that_does_not_exist(self):
        self._state(*HIDDEN['approved + unpaid + ON'])
        hidden = self.customer.get('/customers/artists/get/', {'artist_id': self.profile.artist_id})
        missing = self.customer.get('/customers/artists/get/', {'artist_id': 999999})
        self.assertEqual((hidden.status_code, hidden.data['message']), (missing.status_code, missing.data['message']))

    def test_search_filters_and_pagination_still_work(self):
        self._state(*VISIBLE['approved + exempt + ON'])
        ids = lambda **q: [r['artistId'] for r in self.customer.get('/customers/artists/search/', q).data['data']['data']]
        # (the other artist has no package, so was never listed)
        self.assertEqual(set(ids()), {self.profile.artist_id, self.control.artist_id})
        self.assertEqual(set(ids(max_price=1000)), {self.control.artist_id})
        self.assertEqual(set(ids(min_price=1500)), {self.profile.artist_id})
        self.assertEqual(len(ids(limit=1)), 1)
        self.assertEqual(set(ids(sub_category_id=self.sub.sub_category_id)), {self.profile.artist_id})

    # --- access that must NOT change
    def test_the_owner_always_sees_their_own_data_whatever_the_state(self):
        for name, state in {**VISIBLE, **HIDDEN}.items():
            with self.subTest(name):
                self._state(*state)
                for url in ('/artists/profile/get/', '/artists/packages/get_all/', '/artists/portfolio/get_all/',
                            '/artists/addons/get_all/', '/artists/service_areas/get_all/', '/artists/services/get_all/',
                            '/artists/locations/get_all/', '/artists/profile/specialities/get_all/'):
                    self.assertEqual(self.owner.get(url).status_code, 200, f'{name}: {url}')
                    self.assertEqual(
                        self.owner.get(url, {'artist_id': self.profile.artist_id}).status_code, 200, f'{name}: {url}?artist_id=own')

    def test_an_admin_can_still_open_every_artist_whatever_the_state(self):
        admin, _ = make_admin_client(phone_number='+919900010009')
        for name, state in {**VISIBLE, **HIDDEN}.items():
            with self.subTest(name):
                self._state(*state)
                detail = admin.get('/admin-panel/artists/review/get/', {'artist_id': self.profile.artist_id})
                self.assertEqual(detail.status_code, 200, name)
                rows = admin.get('/admin-panel/artists/get_all/').data['data']['data']
                self.assertIn(self.profile.artist_id, [row['artistId'] for row in rows])

    def test_switching_bookings_back_on_makes_a_paid_artist_visible_again(self):
        self._state(*HIDDEN['approved + paid + OFF'])
        self.assertFalse(self._seen_by(self.customer)['detail'])
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(is_accepting_bookings=True)
        self.assertTrue(self._seen_by(self.customer)['detail'])

    def test_a_refund_hides_the_artist_at_once_without_any_other_change(self):
        self._state(*VISIBLE['approved + paid + ON'])
        self.assertTrue(self._seen_by(self.customer)['search'])
        ArtistRegistrationPayment.objects.filter(artist=self.profile).update(refund_requested_at=timezone.now())
        self.assertFalse(self._seen_by(self.customer)['search'])
