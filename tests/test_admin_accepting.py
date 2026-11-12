"""Admin control of an artist's Booking Accepting, and the Admin view of approval / payment / bookings state.
PUT /admin-panel/artists/accepting_bookings/, GET /admin-panel/artists/get_all/, GET .../artists/review/get/."""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.notifications.models.notification import Notification
from tests.test_admin_panel import make_admin_client
from tests.test_customers import make_artist, make_customer, seed_payment_statuses

TOGGLE = '/admin-panel/artists/accepting_bookings/'
LIST = '/admin-panel/artists/get_all/'
DETAIL = '/admin-panel/artists/review/get/'
ARTIST_TOGGLE = '/artists/profile/accepting_bookings/'


class AdminAcceptingBase(TestCase):

    def setUp(self):
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.admin, _ = make_admin_client(phone_number='+919400000901')
        self.n = 0

    def _artist(self, approval='approved', exempt=False, paid=False, voided=False, locked=False, accepting=False):
        self.n += 1
        client, user, profile = make_artist(phone_number=f'+9199000090{self.n:02d}', name=f'Artist {self.n}', approved=False)
        profile.approval_status = ApprovalStatus.objects.get(name=approval)
        profile.registration_fee_exempt = exempt
        profile.accepting_locked_by_admin = locked
        profile.is_accepting_bookings = accepting
        profile.save()
        if paid or voided:
            self._payment(profile, paid_at=timezone.now(), voided=voided)
        return client, user, profile

    def _payment(self, profile, paid_at=None, voided=False, status='pending', order=None):
        return ArtistRegistrationPayment.objects.create(
            artist=profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=PaymentStatus.objects.get(name=status), paid_at=paid_at, gateway_order_id=order,
            refund_requested_at=timezone.now() if voided else None,
        )

    def _toggle(self, profile, on, client=None):
        return (client or self.admin).put(TOGGLE, {'artist_id': profile.artist_id, 'is_accepting_bookings': on}, format='json')

    def _fresh(self, profile):
        return ArtistProfile.objects.get(artist_id=profile.artist_id)


class AdminToggleTest(AdminAcceptingBase):

    # --- OFF
    def test_admin_can_switch_a_live_artist_off_and_the_artist_is_told(self):
        _, user, profile = self._artist(paid=True, accepting=True)
        resp = self._toggle(profile, False)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data'], {'artistId': profile.artist_id, 'isAcceptingBookings': False, 'acceptingLockedByAdmin': True})
        fresh = self._fresh(profile)
        self.assertEqual((fresh.is_accepting_bookings, fresh.accepting_locked_by_admin), (False, True))
        self.assertTrue(Notification.objects.filter(user_id=user.user_id, title='Bookings switched off').exists())

    def test_an_artist_cannot_override_an_admin_off(self):
        client, _, profile = self._artist(paid=True, accepting=True)
        self._toggle(profile, False)
        resp = client.put(ARTIST_TOGGLE, {'is_accepting_bookings': True}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.accepting_locked_by_admin, resp.data['message'])
        self.assertFalse(self._fresh(profile).is_accepting_bookings)

    def test_admin_can_switch_off_any_artist_including_an_unpaid_or_unapproved_one(self):
        for kwargs in (dict(), dict(approval='pending'), dict(approval='suspended', paid=True)):
            _, _, profile = self._artist(accepting=True, **kwargs)
            self.assertEqual(self._toggle(profile, False).status_code, 200)
            self.assertEqual((self._fresh(profile).is_accepting_bookings, self._fresh(profile).accepting_locked_by_admin), (False, True))

    def test_a_repeated_off_changes_nothing_and_does_not_notify_twice(self):
        _, user, profile = self._artist(paid=True, accepting=True)
        self._toggle(profile, False)
        self.assertEqual(self._toggle(profile, False).status_code, 200)
        self.assertEqual(Notification.objects.filter(user_id=user.user_id, title='Bookings switched off').count(), 1)

    # --- ON
    def test_admin_can_switch_on_an_approved_paid_artist_and_it_clears_the_lock(self):
        _, user, profile = self._artist(paid=True, locked=True)
        resp = self._toggle(profile, True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data'], {'artistId': profile.artist_id, 'isAcceptingBookings': True, 'acceptingLockedByAdmin': False})
        self.assertTrue(Notification.objects.filter(user_id=user.user_id, title='Bookings switched on').exists())

    def test_after_the_admin_switches_back_on_the_artist_controls_it_again(self):
        client, _, profile = self._artist(paid=True, accepting=True)
        self._toggle(profile, False)
        self._toggle(profile, True)
        self.assertEqual(client.put(ARTIST_TOGGLE, {'is_accepting_bookings': False}, format='json').status_code, 200)
        self.assertEqual(client.put(ARTIST_TOGGLE, {'is_accepting_bookings': True}, format='json').status_code, 200)

    def test_admin_can_switch_on_an_exempt_approved_artist(self):
        _, _, profile = self._artist(exempt=True)
        self.assertEqual(self._toggle(profile, True).status_code, 200)
        self.assertTrue(self._fresh(profile).is_accepting_bookings)

    def test_admin_cannot_switch_on_an_unpaid_artist(self):
        _, _, profile = self._artist(locked=True)
        resp = self._toggle(profile, True)
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.admin_accepting_requires_payment, resp.data['message'])
        fresh = self._fresh(profile)
        self.assertEqual((fresh.is_accepting_bookings, fresh.accepting_locked_by_admin), (False, True))   # untouched

    def test_admin_cannot_switch_on_when_the_payment_was_only_started_failed_or_refunded(self):
        started = self._artist()[2]
        self._payment(started, order='order_started')
        failed = self._artist()[2]
        self._payment(failed, status='failed', order='order_failed')
        refunded = self._artist(voided=True)[2]
        for profile in (started, failed, refunded):
            resp = self._toggle(profile, True)
            self.assertEqual(resp.status_code, 400)
            self.assertIn(Constants.admin_accepting_requires_payment, resp.data['message'])
            self.assertFalse(self._fresh(profile).is_accepting_bookings)

    def test_admin_cannot_switch_on_an_unapproved_or_suspended_artist(self):
        for approval, message in (('pending', Constants.admin_accepting_requires_approval),
                                  ('rejected', Constants.admin_accepting_requires_approval),
                                  ('suspended', Constants.artist_suspended)):
            _, _, profile = self._artist(approval=approval, paid=True)
            resp = self._toggle(profile, True)
            self.assertEqual(resp.status_code, 400)
            self.assertIn(message, resp.data['message'])
            self.assertFalse(self._fresh(profile).is_accepting_bookings)

    # --- who may call it
    def test_only_an_admin_may_use_it(self):
        artist_client, _, profile = self._artist(paid=True, accepting=True)
        customer, _ = make_customer(phone_number='+919900009990')
        for client in (artist_client, customer):
            self.assertEqual(self._toggle(profile, False, client=client).status_code, 400)
        self.assertEqual(self._toggle(profile, False, client=APIClient()).status_code, 401)
        self.assertTrue(self._fresh(profile).is_accepting_bookings)

    def test_an_unknown_artist_is_refused(self):
        resp = self.admin.put(TOGGLE, {'artist_id': 999999, 'is_accepting_bookings': False}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.artist_not_found, resp.data['message'])

    def test_the_request_must_say_on_or_off(self):
        _, _, profile = self._artist(paid=True, accepting=True)
        self.assertEqual(self.admin.put(TOGGLE, {'artist_id': profile.artist_id}, format='json').status_code, 400)


class AdminArtistListTest(AdminAcceptingBase):

    def _rows(self, **query):
        resp = self.admin.get(LIST, query)
        self.assertEqual(resp.status_code, 200, resp.data)
        return resp.data['data']['data']

    def _ids(self, **query):
        return {row['artistId'] for row in self._rows(**query)}

    def setUp(self):
        super().setUp()
        self.live = self._artist(paid=True, accepting=True)[2]                 # approved, paid, ON
        self.exempt = self._artist(exempt=True, accepting=True)[2]             # approved, exempt, ON
        self.approved_unpaid = self._artist()[2]                               # approved, unpaid, OFF
        self.paid_off = self._artist(paid=True)[2]                             # approved, paid, OFF
        self.pending_unpaid = self._artist(approval='pending')[2]
        self.rejected = self._artist(approval='rejected', paid=True)[2]
        self.refunded = self._artist(voided=True)[2]                           # approved, refunded, OFF

    def test_the_list_includes_approved_artists_not_just_the_review_queue(self):
        self.assertEqual(self._ids(), {p.artist_id for p in (
            self.live, self.exempt, self.approved_unpaid, self.paid_off, self.pending_unpaid, self.rejected, self.refunded)})

    def test_approved_artists_with_the_payment_pending_can_be_found_in_one_call(self):
        self.assertEqual(
            self._ids(approval_status='approved', registration='unpaid'),
            {self.approved_unpaid.artist_id, self.refunded.artist_id},
        )

    def test_the_registration_filter(self):
        self.assertEqual(self._ids(registration='paid'), {self.live.artist_id, self.paid_off.artist_id, self.rejected.artist_id})
        self.assertEqual(self._ids(registration='exempt'), {self.exempt.artist_id})
        self.assertEqual(self._ids(registration='unpaid'), {
            self.approved_unpaid.artist_id, self.pending_unpaid.artist_id, self.refunded.artist_id})

    def test_the_approval_and_accepting_filters(self):
        self.assertEqual(self._ids(approval_status='pending'), {self.pending_unpaid.artist_id})
        self.assertEqual(self._ids(approval_status='rejected'), {self.rejected.artist_id})
        self.assertEqual(self._ids(accepting='true'), {self.live.artist_id, self.exempt.artist_id})
        self.assertEqual(self._ids(approval_status='approved', registration='paid', accepting='false'), {self.paid_off.artist_id})

    def test_each_row_carries_the_four_separate_states_and_visibility(self):
        rows = {row['artistId']: row for row in self._rows()}
        live = rows[self.live.artist_id]
        self.assertEqual(
            (live['approvalStatus'], live['registrationFeePaid'], live['registrationFeeExempt'], live['registrationEligible'],
             live['isAcceptingBookings'], live['acceptingLockedByAdmin'], live['visibleToCustomers']),
            ('approved', True, False, True, True, False, True),
        )
        self.assertTrue(rows[self.exempt.artist_id]['visibleToCustomers'])
        for hidden in (self.approved_unpaid, self.paid_off, self.pending_unpaid, self.rejected, self.refunded):
            self.assertFalse(rows[hidden.artist_id]['visibleToCustomers'], hidden.artist_id)
        self.assertFalse(rows[self.refunded.artist_id]['registrationFeePaid'])        # a refunded payment does not count
        self.assertIn('fullName', live)
        self.assertIn('phoneNumber', live)

    def test_a_locked_artist_shows_as_locked(self):
        self._toggle(self.live, False)
        row = next(r for r in self._rows() if r['artistId'] == self.live.artist_id)
        self.assertEqual((row['isAcceptingBookings'], row['acceptingLockedByAdmin'], row['visibleToCustomers']), (False, True, False))

    def test_search_and_pagination(self):
        user = self.live.user
        self.assertEqual(self._ids(search_key=user.name), {self.live.artist_id})
        self.assertEqual(self._ids(search_key=user.phone_number[-8:]), {self.live.artist_id})
        first = self.admin.get(LIST, {'limit': 3, 'page_num': 1}).data['data']
        second = self.admin.get(LIST, {'limit': 3, 'page_num': 2}).data['data']
        self.assertEqual((len(first['data']), first['totalPage']), (3, 3))
        self.assertTrue(set(r['artistId'] for r in first['data']).isdisjoint(r['artistId'] for r in second['data']))
        self.assertEqual(self.admin.get(LIST, {'limit': 3, 'page_num': 9}).status_code, 400)

    def test_an_unknown_filter_value_is_refused(self):
        self.assertEqual(self.admin.get(LIST, {'registration': 'maybe'}).status_code, 400)
        self.assertEqual(self.admin.get(LIST, {'approval_status': 'nope'}).status_code, 400)

    def test_only_an_admin_may_list(self):
        artist_client = self._artist(paid=True)[0]
        customer, _ = make_customer(phone_number='+919900009991')
        for client in (artist_client, customer):
            self.assertEqual(client.get(LIST).status_code, 400)
        self.assertEqual(APIClient().get(LIST).status_code, 401)


class AdminArtistDetailAndOwnProfileTest(AdminAcceptingBase):

    def test_the_review_detail_shows_eligibility_and_bookings_state(self):
        _, _, profile = self._artist(paid=True, locked=True)
        data = self.admin.get(DETAIL, {'artist_id': profile.artist_id}).data['data']
        self.assertEqual(
            (data['registrationEligible'], data['isAcceptingBookings'], data['acceptingLockedByAdmin']), (True, False, True))
        _, _, unpaid = self._artist()
        data = self.admin.get(DETAIL, {'artist_id': unpaid.artist_id}).data['data']
        self.assertFalse(data['registrationEligible'])

    def test_the_artist_sees_their_own_lock_and_eligibility(self):
        client, _, profile = self._artist(paid=True, locked=True)
        data = client.get('/artists/profile/get/').data['data']
        self.assertEqual((data['acceptingLockedByAdmin'], data['registrationEligible'], data['isAcceptingBookings']), (True, True, False))
        unpaid_client, _, _ = self._artist()
        self.assertFalse(unpaid_client.get('/artists/profile/get/').data['data']['registrationEligible'])

    def test_other_users_never_see_the_lock_or_the_payment_state(self):
        # A visible artist (approved, paid, bookings on, not locked): other users see the public profile only.
        _, _, profile = self._artist(paid=True, accepting=True)
        customer, _ = make_customer(phone_number='+919900009992')
        other_artist = self._artist(paid=True)[0]
        for client in (customer, other_artist):
            data = client.get('/artists/profile/get/', {'artist_id': profile.artist_id}).data['data']
            self.assertNotIn('acceptingLockedByAdmin', data)
            self.assertNotIn('registrationEligible', data)
            resp = client.get('/artists/profile/get/', {'artist_id': profile.artist_id, 'values': 'registrationEligible'})
            self.assertEqual(resp.status_code, 400)

    def test_an_artist_the_admin_locked_out_is_not_found_by_other_users(self):
        # Locked means hidden, even if the stored switch still says on: there is nothing to leak because there is no page.
        _, _, locked = self._artist(paid=True, locked=True, accepting=True)
        customer, _ = make_customer(phone_number='+919900009993')
        other_artist = self._artist(paid=True)[0]
        for client in (customer, other_artist):
            resp = client.get('/artists/profile/get/', {'artist_id': locked.artist_id})
            self.assertEqual(resp.status_code, 400)
            self.assertIn(Constants.data_no_match, resp.data['message'])       # the same answer as for any artist they may not see
