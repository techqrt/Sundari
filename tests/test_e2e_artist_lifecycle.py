"""End-to-end lifecycle of an artist, from sign-up to going live, to being switched off and rejected, with a customer
booking along the way. Everything goes through the real HTTP endpoints (sign-up, onboarding, admin panel, payments,
bookings); only the Razorpay gateway is faked, by a small stateful fake that refuses to settle a payment nobody
captured. The test also fails on any unexpected ERROR log, so a swallowed exception cannot hide behind a green run.

The facts it holds together: admin approval, registration payment, the bookings switch and customer visibility are
four separate things. Approval never needs payment, payment never approves and never switches bookings on, and an
artist is visible to customers only when all three hold."""
import hashlib
import hmac
import json
import logging
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from sunndari.config import Configurations
from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment, PromoCode, PromoRedemption
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.customers.models import Booking
from sunndari_apps.notifications.models.notification import Notification
from tests.booking_address import address_for
from tests.test_admin_panel import make_admin_client, verify_id_proof
from tests.test_artists import complete_onboarding_steps
from tests.test_customers import make_customer, next_weekday, seed_booking_statuses, seed_payment_statuses

WEBHOOK = '/customers/payments/webhook/razorpay/'
SECRET = 'whsec_e2e'
GATEWAY = 'sunndari_apps.payments.gateway.RazorpayGateway.get_client'
# Logged by the Firestore sync, which is switched off under the test runner by design.
EXPECTED_NOISE = ('Firestore', 'Firebase')


class _ErrorCollector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def make_gateway():
    """A stateful stand-in for Razorpay: orders are created, can be paid (captured), fetched, and refunded."""
    gw = MagicMock()
    gw.orders, gw.payments, gw.refunds = {}, {}, []

    def create(data):
        order = {'id': f"order_{data['receipt']}", 'amount': data['amount'], 'amount_paid': 0,
                 'currency': data['currency'], 'status': 'created'}
        gw.orders[order['id']] = order
        return order

    def fetch_payment(payment_id):
        if payment_id not in gw.payments:               # the gateway has never heard of it, like the real one
            import razorpay
            raise razorpay.errors.BadRequestError('The id provided does not exist')
        return gw.payments[payment_id]

    def refund(payment_id, data):
        gw.refunds.append((payment_id, data))
        return {'id': f'rfnd_{len(gw.refunds)}'}

    def pay(order_id, payment_id=None):
        """The customer completes Checkout: the order is paid and the payment captured."""
        order = gw.orders[order_id]
        payment_id = payment_id or f'pay_{len(gw.payments) + 1}'
        order.update({'amount_paid': order['amount'], 'status': 'paid'})
        gw.payments[payment_id] = {'id': payment_id, 'order_id': order_id, 'status': 'captured',
                                   'amount': order['amount'], 'currency': order['currency']}
        return payment_id

    gw.order.create.side_effect = create
    gw.order.fetch.side_effect = lambda oid: gw.orders[oid]
    gw.payment.fetch.side_effect = fetch_payment
    gw.payment.refund.side_effect = refund
    gw.utility.verify_payment_signature.return_value = None
    gw.pay = pay
    return gw


class E2EBase(TestCase):

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.gw = make_gateway()
        for patcher in (patch(GATEWAY, return_value=self.gw), patch.object(Configurations, 'razorpay_webhook_secret', SECRET)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.errors = _ErrorCollector()
        logging.getLogger().addHandler(self.errors)
        self.addCleanup(logging.getLogger().removeHandler, self.errors)
        self.admin, _ = make_admin_client(phone_number='+919800000001')
        self.customer, self.customer_user = make_customer(phone_number='+919800000002')
        self.date = next_weekday(0)                  # the onboarding helper gives the artist a Monday schedule
        self.hour = 8

    def tearDown(self):
        unexpected = [r for r in self.errors.records if not any(word in r.getMessage() for word in EXPECTED_NOISE)]
        self.assertEqual(unexpected, [], 'unexpected ERROR logs: ' + '; '.join(r.getMessage()[:160] for r in unexpected))

    # --- actors
    def sign_up_artist(self, phone):
        client = APIClient()
        resp = client.post('/auth/register/', {'name': 'Asha Verma', 'phone_number': phone,
                                               'password': 'securepass123', 'role': 'artist'})
        self.assertEqual(resp.status_code, 200, resp.data)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['data']['access_token']}")
        user = User.objects.get(phone_number=phone)
        return client, user, ArtistProfile.objects.get(user_id=user.user_id)

    def profile(self, profile):
        return ArtistProfile.objects.get(artist_id=profile.artist_id)

    # --- what customers can see of the artist, on every path
    def seen_by_customer(self, profile, slug=None):
        aid = profile.artist_id
        ok = lambda r: r.status_code == 200
        get = lambda url, **q: self.customer.get(url, {'artist_id': aid, **q})
        search = self.customer.get('/customers/artists/search/').data['data']['data']
        return {
            'search': any(row['artistId'] == aid for row in search),
            'detail': ok(get('/customers/artists/get/')),
            'availability': ok(get('/customers/artists/availability/', booking_date=self.date.strftime('%d-%m-%y'))),
            'profile': ok(get('/artists/profile/get/')),
            'packages': ok(get('/artists/packages/get_all/')),
            'services': ok(get('/artists/services/get_all/')),
            'locations': ok(get('/artists/locations/get_all/')),
            'public page': ok(APIClient().get('/public/artists/get/', {'slug': slug})) if slug else None,
        }

    def assert_visible(self, profile, slug=None, expected=True):
        seen = {k: v for k, v in self.seen_by_customer(profile, slug).items() if v is not None}
        verdict = all(seen.values()) if expected else not any(seen.values())
        self.assertTrue(verdict, f"{'visible' if expected else 'hidden'} expected, got {seen}")

    def _live_artist(self, phone='+919234500010'):
        """Signed up, fully onboarded, submitted and approved by an admin, but NOT yet paid and with bookings OFF."""
        artist, user, profile = self.sign_up_artist(phone)
        complete_onboarding_steps(artist, user, pay_fee=False)
        artist.post('/artists/onboarding/submit/', {}, format='json')
        verify_id_proof(self.admin, profile)
        self.admin.put('/admin-panel/artists/approve/', {'artist_id': profile.artist_id}, format='json')
        return artist, user, profile

    # --- bookings
    def book(self, profile, expect=201):
        self.hour += 2
        from sunndari_apps.artists.models import ArtistLocationPreference, PricingPackage
        location_type_id = ArtistLocationPreference.objects.filter(artist_id=profile.artist_id).first().location_type_id
        package = PricingPackage.objects.filter(artist_id=profile.artist_id, is_active=True).first()
        resp = self.customer.post('/customers/bookings/create/', {
            **address_for(self.customer), 'artist_id': profile.artist_id, 'package_id': package.package_id,
            'location_type_id': location_type_id, 'booking_date': self.date.strftime('%d-%m-%y'),
            'start_time': f'{self.hour:02d}:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, expect, resp.data)
        return resp.data['data']['booking_id'] if expect == 201 else resp

    def pay_booking(self, booking_id):
        init = self.customer.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json')
        self.assertIn(init.status_code, (200, 201), init.data)
        order_id = init.data['data']['gateway_order_id']
        payment_id = self.gw.pay(order_id)
        verify = self.customer.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(verify.status_code, 200, verify.data)
        return payment_id

    def artist_sets(self, client, booking_id, status):
        return client.put('/artists/bookings/update_status/', {'booking_id': booking_id, 'status': status}, format='json')

    def booking_status(self, booking_id):
        return Booking.objects.get(booking_id=booking_id).status.name

    # --- the artist's own switch
    def artist_switch(self, client, on):
        return client.put('/artists/profile/accepting_bookings/', {'is_accepting_bookings': on}, format='json')

    def admin_switch(self, profile, on):
        return self.admin.put('/admin-panel/artists/accepting_bookings/',
                              {'artist_id': profile.artist_id, 'is_accepting_bookings': on}, format='json')

    # --- registration payment
    def pay_registration(self, client, promo=None):
        resp = client.post('/artists/registration/payment/initiate/', {'promo_code': promo} if promo else {}, format='json')
        self.assertIn(resp.status_code, (200, 201), resp.data)
        data = resp.data['data']
        if data['fully_covered_by_promo']:
            return data, None
        payment_id = self.gw.pay(data['gateway_order_id'])
        verify = client.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': data['gateway_order_id'], 'razorpay_payment_id': payment_id,
            'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(verify.status_code, 200, verify.data)
        return data, payment_id


class ArtistLifecycleE2ETest(E2EBase):

    def test_the_whole_lifecycle(self):
        # ── 1. Sign-up through the real endpoint ───────────────────────────────
        artist, user, profile = self.sign_up_artist('+919234500001')
        p = self.profile(profile)
        self.assertEqual((p.approval_status.name, p.is_accepting_bookings, p.registration_fee_exempt,
                          p.accepting_locked_by_admin), ('pending', False, False, False))
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        own = artist.get('/artists/profile/get/').data['data']
        self.assertEqual((own['isAcceptingBookings'], own['registrationEligible'], own['acceptingLockedByAdmin']),
                         (False, False, False))

        # ── 2. Onboarding without paying: every other step, then submit ────────
        complete_onboarding_steps(artist, user, pay_fee=False)
        steps = artist.get('/artists/onboarding/status/').data['data']['steps']
        self.assertFalse(steps['registrationFee'])
        self.assertTrue(all(done for name, done in steps.items() if name != 'registrationFee'))
        slug = ArtistProfile.ensure_public_slug(user.user_id)
        self.assert_visible(profile, slug, expected=False)                       # nothing is visible yet
        self.assertEqual(artist.post('/artists/onboarding/submit/', {}, format='json').status_code, 200)
        self.assertEqual(artist.get('/artists/onboarding/status/').data['data']['status'], 'submitted')

        # ── 3. Admin sees the artist (unpaid, pending) and approves without payment ──
        rows = self.admin.get('/admin-panel/artists/get_all/', {'approval_status': 'pending', 'registration': 'unpaid'}).data['data']['data']
        self.assertEqual([r['artistId'] for r in rows], [profile.artist_id])
        verify_id_proof(self.admin, profile)
        self.assertEqual(self.admin.put('/admin-panel/artists/approve/', {'artist_id': profile.artist_id}, format='json').status_code, 200)
        p = self.profile(profile)
        self.assertEqual((p.approval_status.name, p.is_accepting_bookings), ('approved', False))
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0, 'approving must never start a payment')
        self.assertIn('registration payment', Notification.objects.get(user_id=user.user_id, type='artist_approved').message)
        unpaid_approved = self.admin.get('/admin-panel/artists/get_all/', {'approval_status': 'approved', 'registration': 'unpaid'}).data['data']['data']
        self.assertEqual([r['artistId'] for r in unpaid_approved], [profile.artist_id])
        self.assertFalse(unpaid_approved[0]['visibleToCustomers'])
        self.assert_visible(profile, slug, expected=False)                       # approved but unpaid: hidden

        # ── 4. Blockers: nobody can switch bookings on for an unpaid artist ────
        refused = self.artist_switch(artist, True)
        self.assertEqual(refused.status_code, 400)
        self.assertIn(Constants.accepting_requires_payment, refused.data['message'])
        refused = self.admin_switch(profile, True)
        self.assertEqual(refused.status_code, 400)
        self.assertIn(Constants.admin_accepting_requires_payment, refused.data['message'])
        self.book(profile, expect=400)                                           # and a customer cannot book them

        # ── 5. Registration payment with a 25% code ────────────────────────────
        PromoCode.objects.create(code='Q25', discount_percent=25)
        preview = artist.post('/artists/registration/promo/validate/', {'promo_code': 'q25'}, format='json').data['data']
        self.assertEqual((preview['discountAmount'], preview['payableAmount']), ('499.75', '1499.25'))
        started = artist.post('/artists/registration/payment/initiate/', {'promo_code': 'Q25'}, format='json').data['data']
        self.assertEqual((started['amount'], started['payable_amount']), (149925, '1499.25'))
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id), 'a started payment must not make the artist eligible')
        self.assertEqual(self.artist_switch(artist, True).status_code, 400)
        order_id = started['gateway_order_id']
        unpaid_verify = artist.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_never_captured', 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(unpaid_verify.status_code, 400)                          # the gateway has no such payment
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        payment_id = self.gw.pay(order_id)
        ok = artist.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        again = artist.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual((again.status_code, again.data['message']), (200, 'Payment already verified'))
        self.assertEqual(ArtistRegistrationPayment.objects.filter(artist=profile, paid_at__isnull=False).count(), 1)
        self.assertEqual(PromoRedemption.objects.filter(artist=profile, status='redeemed').count(), 1)
        self.assertEqual(artist.post('/artists/registration/payment/initiate/', {}, format='json').status_code, 400)   # already paid

        # ── 6. Paid is eligible, not live: bookings stay OFF until the artist chooses ──
        p = self.profile(profile)
        self.assertTrue(ArtistProfile.is_eligible(profile.artist_id))
        self.assertFalse(p.is_accepting_bookings)
        self.assert_visible(profile, slug, expected=False)
        self.assertEqual(self.artist_switch(artist, True).status_code, 200)
        self.assert_visible(profile, slug, expected=True)                        # approved + paid + ON: visible everywhere
        listed = self.admin.get('/admin-panel/artists/get_all/').data['data']['data'][0]
        self.assertTrue(listed['visibleToCustomers'])

        # ── 7. A customer books, pays, and the artist accepts ──────────────────
        first = self.book(profile)
        self.pay_booking(first)
        self.assertEqual(self.artist_sets(artist, first, 'confirmed').status_code, 200)
        second = self.book(profile)                                              # a second request, paid, waiting
        self.pay_booking(second)
        third = self.book(profile)                                               # a third, still unpaid
        self.assertEqual(self.booking_status(first), 'confirmed')

        # ── 8. Admin switches the artist off: hidden, blocked, nothing existing disturbed ──
        self.assertEqual(self.admin_switch(profile, False).status_code, 200)
        self.assert_visible(profile, slug, expected=False)
        self.book(profile, expect=400)
        blocked = self.artist_sets(artist, second, 'confirmed')
        self.assertEqual(blocked.status_code, 400)
        self.assertIn(Constants.accepting_locked_by_admin, blocked.data['message'])
        undo = self.artist_switch(artist, True)
        self.assertEqual(undo.status_code, 400)
        self.assertIn(Constants.accepting_locked_by_admin, undo.data['message'])
        self.assertEqual(self.booking_status(first), 'confirmed')                # the confirmed booking is untouched
        self.assertEqual(self.customer.get('/customers/bookings/get/', {'booking_id': first}).status_code, 200)
        declined = self.artist_sets(artist, second, 'cancelled')                 # the artist can still decline: refund
        self.assertEqual(declined.status_code, 200)
        self.assertEqual(self.booking_status(second), 'cancelled')
        self.assertTrue(self.gw.refunds, 'declining a paid request must refund it')

        # ── 9. Admin switches back on; the artist controls it again ────────────
        self.assertEqual(self.admin_switch(profile, True).status_code, 200)
        self.assert_visible(profile, slug, expected=True)
        self.assertEqual(self.artist_switch(artist, False).status_code, 200)
        self.assert_visible(profile, slug, expected=False)
        self.assertEqual(self.artist_switch(artist, True).status_code, 200)

        # ── 10. Rejection: fee refunded, bookings off, hidden, promo released ──
        refunds_before = len(self.gw.refunds)
        reject = self.admin.put('/admin-panel/artists/reject/', {'artist_id': profile.artist_id, 'reason': 'Re-check'}, format='json')
        self.assertEqual(reject.status_code, 200, reject.data)
        p = self.profile(profile)
        self.assertEqual((p.approval_status.name, p.is_accepting_bookings), ('rejected', False))
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        self.assert_visible(profile, slug, expected=False)
        refund_calls = self.gw.refunds[refunds_before:]
        self.assertEqual(len(refund_calls), 1)
        self.assertEqual((refund_calls[0][0], refund_calls[0][1]['amount']), (payment_id, 149925))
        self.assertEqual(PromoRedemption.objects.filter(artist=profile, status='released').count(), 1)
        self.assertEqual(self.booking_status(first), 'confirmed')                # still intact after the rejection
        self.assertEqual(self.booking_status(third), 'pending')

        # ── 11. Resubmit, re-approve, pay again: eligible but still OFF until the artist chooses ──
        self.assertEqual(artist.post('/artists/onboarding/submit/', {}, format='json').status_code, 200)
        self.assertEqual(self.admin.put('/admin-panel/artists/approve/', {'artist_id': profile.artist_id}, format='json').status_code, 200)
        self.assertEqual(self.artist_switch(artist, True).status_code, 400)       # unpaid again
        self.pay_registration(artist, promo='Q25')                                # the released code can be used again
        self.assertTrue(ArtistProfile.is_eligible(profile.artist_id))
        self.assertFalse(self.profile(profile).is_accepting_bookings)
        self.assert_visible(profile, slug, expected=False)
        self.assertEqual(self.artist_switch(artist, True).status_code, 200)
        self.assert_visible(profile, slug, expected=True)
        self.assertEqual(len(self.gw.refunds), refunds_before + 1, 'no second refund')


class LogicChecksE2ETest(E2EBase):

    def test_a_100_percent_code_makes_the_artist_eligible_without_the_gateway(self):
        artist, user, profile = self._live_artist()
        PromoCode.objects.create(code='FREE', discount_percent=100)
        data, payment_id = self.pay_registration(artist, promo='FREE')
        self.assertTrue(data['fully_covered_by_promo'])
        self.assertEqual(self.gw.order.create.call_count, 0, 'a free registration must never call the gateway')
        record = ArtistRegistrationPayment.objects.get(artist=profile)
        self.assertEqual((record.gateway, str(record.payable_amount)), ('promo', '0.00'))
        self.assertTrue(ArtistProfile.is_eligible(profile.artist_id))
        self.assertFalse(self.profile(profile).is_accepting_bookings)
        self.assertEqual(self.artist_switch(artist, True).status_code, 200)

    def test_every_discount_pays_the_amount_the_server_calculated(self):
        for percent, paise in ((25, 149925), (50, 99950), (75, 49975)):
            artist, user, profile = self.sign_up_artist(f'+9192345001{percent}')
            PromoCode.objects.create(code=f'P{percent}', discount_percent=percent)
            data, _ = self.pay_registration(artist, promo=f'P{percent}')
            self.assertEqual(data['amount'], paise, percent)
            self.assertTrue(ArtistProfile.is_eligible(profile.artist_id), percent)
        artist, user, profile = self.sign_up_artist('+919234500199')
        data, _ = self.pay_registration(artist)
        self.assertEqual(data['amount'], 199900)

    def test_a_client_cannot_name_its_own_price(self):
        artist, user, profile = self.sign_up_artist('+919234500020')
        resp = artist.post('/artists/registration/payment/initiate/',
                           {'amount': 1, 'payable_amount': '1.00', 'discount_percent': 100, 'fee_amount': '1.00'}, format='json')
        self.assertIn(resp.status_code, (200, 201))
        self.assertEqual(resp.data['data']['amount'], 199900)
        self.assertFalse(resp.data['data']['fully_covered_by_promo'])

    def test_an_artist_cannot_grant_themselves_anything_through_the_profile_update(self):
        artist, user, profile = self.sign_up_artist('+919234500021')
        artist.put('/artists/profile/update/', {
            'registration_fee_exempt': True, 'is_accepting_bookings': True, 'accepting_locked_by_admin': False,
            'approval_status_id': ApprovalStatus.objects.get(name='approved').status_id,
            'commission_rate': '0.00', 'bio': 'hello',
        }, format='json')
        p = self.profile(profile)
        self.assertEqual((p.registration_fee_exempt, p.is_accepting_bookings, p.approval_status.name, p.bio),
                         (False, False, 'pending', 'hello'))

    def test_an_artist_cannot_use_another_artists_payment(self):
        mine, _, my_profile = self.sign_up_artist('+919234500022')
        theirs, _, their_profile = self.sign_up_artist('+919234500023')
        order = theirs.post('/artists/registration/payment/initiate/', {}, format='json').data['data']['gateway_order_id']
        payment_id = self.gw.pay(order)
        stolen = mine.post('/artists/registration/payment/verify/', {
            'razorpay_order_id': order, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(stolen.status_code, 400)
        self.assertFalse(ArtistProfile.is_eligible(my_profile.artist_id))
        self.assertFalse(ArtistProfile.is_eligible(their_profile.artist_id))

    def test_a_customer_or_a_different_artist_cannot_reach_the_admin_controls(self):
        artist, user, profile = self._live_artist()
        other, _, _ = self.sign_up_artist('+919234500024')
        for client in (self.customer, other, artist):
            resp = client.put('/admin-panel/artists/accepting_bookings/',
                              {'artist_id': profile.artist_id, 'is_accepting_bookings': False}, format='json')
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(client.get('/admin-panel/artists/get_all/').status_code, 400)
        self.assertFalse(self.profile(profile).accepting_locked_by_admin)

    def test_the_signed_webhook_settles_once_and_never_switches_bookings_on(self):
        artist, user, profile = self._live_artist()
        data = artist.post('/artists/registration/payment/initiate/', {}, format='json').data['data']
        payment_id = self.gw.pay(data['gateway_order_id'])
        body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': payment_id, 'order_id': data['gateway_order_id'], 'amount': data['amount'],
            'status': 'captured', 'currency': 'INR'}}}}).encode()
        sign = lambda raw, secret=SECRET: hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        post = lambda raw, secret=SECRET: APIClient().generic('POST', WEBHOOK, raw, content_type='application/json',
                                                               HTTP_X_RAZORPAY_SIGNATURE=sign(raw, secret))
        self.assertEqual(post(body, 'wrong-secret').status_code, 400)             # a forged webhook changes nothing
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        self.assertEqual(post(body).status_code, 200)
        self.assertEqual(post(body).status_code, 200)                              # delivered twice
        self.assertEqual(ArtistRegistrationPayment.objects.filter(artist=profile, paid_at__isnull=False).count(), 1)
        self.assertEqual(Notification.objects.filter(user_id=user.user_id, title='Registration fee received').count(), 1)
        self.assertTrue(ArtistProfile.is_eligible(profile.artist_id))
        self.assertFalse(self.profile(profile).is_accepting_bookings)

    def test_a_stored_on_flag_never_makes_an_ineligible_artist_visible_or_able_to_accept(self):
        artist, user, profile = self._live_artist()
        slug = ArtistProfile.ensure_public_slug(user.user_id)
        ArtistProfile.objects.filter(artist_id=profile.artist_id).update(is_accepting_bookings=True)   # e.g. a stray edit
        self.assertFalse(ArtistProfile.is_eligible(profile.artist_id))
        self.assert_visible(profile, slug, expected=False)
        self.book(profile, expect=400)

    def test_an_admin_lock_wins_over_a_stored_on_flag_on_every_path(self):
        artist, user, profile = self._live_artist()
        self.pay_registration(artist)
        self.assertEqual(self.artist_switch(artist, True).status_code, 200)
        slug = ArtistProfile.ensure_public_slug(user.user_id)
        waiting = self.book(profile)
        self.pay_booking(waiting)
        self.assert_visible(profile, slug, expected=True)
        # the two switches disagree: the admin's lock is set but the artist's flag still says ON
        ArtistProfile.objects.filter(artist_id=profile.artist_id).update(accepting_locked_by_admin=True, is_accepting_bookings=True)
        self.assert_visible(profile, slug, expected=False)
        self.book(profile, expect=400)
        blocked = self.artist_sets(artist, waiting, 'confirmed')
        self.assertEqual(blocked.status_code, 400)
        self.assertIn(Constants.accepting_locked_by_admin, blocked.data['message'])

    def test_bad_input_is_refused_not_crashed(self):
        artist, user, profile = self._live_artist()
        for body in ({}, {'is_accepting_bookings': 'maybe'}, {'is_accepting_bookings': None}, {'is_accepting_bookings': []}):
            self.assertEqual(artist.put('/artists/profile/accepting_bookings/', body, format='json').status_code, 400, body)
        for body in ({}, {'artist_id': 'x', 'is_accepting_bookings': True}, {'artist_id': profile.artist_id},
                     {'artist_id': -1, 'is_accepting_bookings': True}, {'artist_id': 10 ** 12, 'is_accepting_bookings': True}):
            self.assertEqual(self.admin.put('/admin-panel/artists/accepting_bookings/', body, format='json').status_code, 400, body)
        for query in ({'registration': 'maybe'}, {'approval_status': 'nope'}, {'accepting': 'perhaps'}, {'page_num': 0},
                      {'limit': 0}, {'limit': 10 ** 6}, {'page_num': 999}):
            self.assertEqual(self.admin.get('/admin-panel/artists/get_all/', query).status_code, 400, query)
        for code in ('', 'x' * 41, '   ', "'; DROP TABLE users;--"):
            resp = artist.post('/artists/registration/promo/validate/', {'promo_code': code}, format='json')
            self.assertEqual(resp.status_code, 400, repr(code))
        self.assertEqual(artist.post('/artists/registration/payment/verify/', {}, format='json').status_code, 400)
        self.assertEqual(ArtistRegistrationPayment.objects.count(), 0)            # none of that created a payment

    def test_hidden_artist_data_does_not_leak_through_the_service_list(self):
        artist, user, profile = self._live_artist()
        names = lambda: [r['name'] for r in self.customer.get('/core/service-sub-category/get_all/').data['data']['data']]
        self.assertEqual(names(), [])                                             # approved but unpaid: not bookable
        self.pay_registration(artist)
        self.assertEqual(names(), [])                                             # paid but OFF
        self.artist_switch(artist, True)
        self.assertEqual(names(), ['Haircut'])
        self.admin_switch(profile, False)
        self.assertEqual(names(), [])
