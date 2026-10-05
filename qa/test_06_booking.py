import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from sunndari_apps.artists.models import ArtistProfile, ArtistAvailabilityBlock, ArtistServiceArea, PackageAddOn
from sunndari_apps.customers.models import Booking, BookingReschedule, Review
from sunndari_apps.payments.models import Payment
from sunndari_apps.wallet.models import CustomerWallet
from sunndari_apps.chat.models import Conversation
from zoneinfo import ZoneInfo
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client, at
from qa import world as w

IST = ZoneInfo('Asia/Kolkata')
F = 'BOOKING'


def ist(day_offset, hh, mm=0):
    d = w.future_date(day_offset)
    return datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).astimezone(datetime.timezone.utc)


class BookingE2EQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.art = w.make_bookable_artist('+919700000001', 'E2E Artist', price=2000)
        cls.cus = w.make_customer('+919700000002', 'E2E Customer')

    def tearDown(self):
        dump()

    def test_full_happy_path(self):
        A, C = self.art, self.cus
        # --- customer discovery
        search = data(C.client.get('/customers/artists/search/')) or {}
        record(F, 'customer discovers the artist in search', A.profile.artist_id in [x['artistId'] for x in search.get('data', [])], 'listed', 'checked', sev='P1')
        det = data(C.client.get('/customers/artists/get/', {'artist_id': A.profile.artist_id})) or {}
        record(F, 'artist detail shows services, packages, add-ons and areas keys', all(k in det for k in ('profile', 'packages', 'services', 'addOns', 'serviceAreas', 'portfolio')), 'all present', sorted(det), sev='P1')
        avail = data(C.client.get('/customers/artists/availability/', {'artist_id': A.profile.artist_id, 'booking_date': w.fmt_date(w.future_date(3))})) or {}
        record(F, 'availability reports the working window for the chosen date', avail.get('workingWindow') is not None and not avail.get('isBlocked'), 'window present', avail, sev='P1')
        # --- create
        r = w.create_booking(C, A, start='10:00:00', day=3)
        bid = (data(r) or {}).get('booking_id')
        record(F, 'customer creates a booking (pending, slot locked)', r.status_code == 201 and bid, 201, r.status_code, sev='P0')
        b = Booking.objects.get(booking_id=bid)
        record(F, 'booking stored with server-computed total and 1h slot', b.total_amount == Decimal('2000.00') and str(b.end_time) == '11:00:00' and b.status.name == 'pending' and b.expires_at, '2000 / 11:00 / pending / lock', (b.total_amount, b.end_time, b.status.name), sev='P0')
        record(F, 'artist receives a new-booking notification and booking OTP', any(n.type == 'new_booking_alert' for n in __import__('sunndari_apps.notifications.models.notification', fromlist=['Notification']).Notification.objects.filter(user_id=A.id)), 'notified', 'checked', sev='P2')
        # --- artist sees it, cannot confirm before payment
        lst = data(A.client.get('/artists/bookings/get_all/')) or {}
        record(F, 'artist sees the booking in their list', bid in [x['bookingId'] for x in lst.get('data', [])], 'listed', 'checked', sev='P0')
        r = A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
        record(F, 'artist cannot confirm an unpaid booking', r.status_code == 400 and Booking.objects.get(booking_id=bid).status.name == 'pending', 'refused', r.status_code, sev='P0')
        w.pay(bid)
        r = A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
        record(F, 'artist confirms after payment', r.status_code == 200 and Booking.objects.get(booking_id=bid).status.name == 'confirmed', 'confirmed', r.status_code, sev='P0')
        # --- on my way: too early / in window
        r = A.client.put('/artists/bookings/on_my_way/', {'booking_id': bid}, format='json')
        record(F, 'on-my-way is refused days before the appointment', r.status_code == 400 and Booking.objects.get(booking_id=bid).on_my_way_at is None, 'refused', r.status_code, sev='P1')
        with at(ist(3, 8, 30)):
            r = A.client.put('/artists/bookings/on_my_way/', {'booking_id': bid}, format='json')
            record(F, 'on-my-way accepted inside the 2h window', r.status_code == 200 and Booking.objects.get(booking_id=bid).on_my_way_at, 'ok', r.status_code, sev='P0')
            r = A.client.put('/artists/bookings/on_my_way/', {'booking_id': bid}, format='json')
            record(F, 'on-my-way cannot be repeated', r.status_code == 400, 400, r.status_code, sev='P3')
            # --- arrived (booking OTP)
            otp = Booking.objects.get(booking_id=bid).booking_otp
            r = A.client.put('/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': (otp % 900000) + 100000 if otp != 111111 else 222222}, format='json')
            record(F, 'arrival with a wrong booking OTP is refused and counted', r.status_code == 400 and Booking.objects.get(booking_id=bid).booking_otp_attempts == 1, 'refused', (r.status_code, Booking.objects.get(booking_id=bid).booking_otp_attempts), sev='P0')
            r = A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': 1234}, format='json')
            record(F, 'start PIN cannot be used before arrival', r.status_code == 400, 400, r.status_code, sev='P0')
            r = A.client.put('/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': otp}, format='json')
            record(F, 'arrival with the correct OTP is accepted', r.status_code == 200 and Booking.objects.get(booking_id=bid).arrived_at, 'ok', r.status_code, sev='P0')
            b = Booking.objects.get(booking_id=bid)
            record(F, 'booking OTP is nulled after use and a start PIN is issued', b.booking_otp is None and b.start_service_pin is not None, 'single-use', (b.booking_otp, bool(b.start_service_pin)), sev='P0')
            r = A.client.put('/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': otp}, format='json')
            record(F, 'used booking OTP cannot be replayed', r.status_code == 400, 400, r.status_code, sev='P0')
            # --- start PIN
            mine = data(C.client.get('/customers/bookings/start_pin/', {'booking_id': bid})) or {}
            pin = Booking.objects.get(booking_id=bid).start_service_pin
            record(F, 'customer can read their start PIN; artist cannot', bool(mine) and not is_2xx(A.client.get('/customers/bookings/start_pin/', {'booking_id': bid})), 'customer only', str(mine)[:80], sev='P0')
            wrong = 1000 if pin != 1000 else 2000
            r = A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': wrong}, format='json')
            record(F, 'wrong start PIN refused', r.status_code == 400 and Booking.objects.get(booking_id=bid).status.name == 'confirmed', 'refused', r.status_code, sev='P0')
            r = A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': pin}, format='json')
            b = Booking.objects.get(booking_id=bid)
            record(F, 'correct start PIN moves the booking to in_progress and consumes the PIN', r.status_code == 200 and b.status.name == 'in_progress' and b.start_service_pin is None and b.completion_pin, 'in_progress, pin nulled', (r.status_code, b.status.name), sev='P0')
            r = A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': pin}, format='json')
            record(F, 'start PIN cannot be reused', r.status_code == 400, 400, r.status_code, sev='P0')
            # --- completion
            r = A.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid, 'completion_pin': 1}, format='json')
            record(F, 'a wrong completion PIN is refused', r.status_code == 400 and Booking.objects.get(booking_id=bid).status.name == 'in_progress', 'refused', r.status_code, sev='P0')
            cpin = Booking.objects.get(booking_id=bid).completion_pin
            coins_before = CustomerWallet.objects.filter(customer_id=C.id).values_list('balance_coins', flat=True).first() or 0
            r = A.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid, 'completion_pin': cpin}, format='json')
            b = Booking.objects.get(booking_id=bid)
            record(F, 'correct completion PIN completes the booking and consumes the PIN', r.status_code == 200 and b.status.name == 'completed' and b.completion_pin is None and b.service_completed_at, 'completed', (r.status_code, b.status.name), sev='P0')
            coins_after = CustomerWallet.objects.filter(customer_id=C.id).values_list('balance_coins', flat=True).first() or 0
            record(F, 'cashback coins credited exactly once on completion', coins_after > coins_before, 'credited', (coins_before, coins_after), sev='P1')
            r = A.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid, 'completion_pin': cpin}, format='json')
            coins_replay = CustomerWallet.objects.filter(customer_id=C.id).values_list('balance_coins', flat=True).first() or 0
            record(F, 'completion PIN replay refused and cashback not paid twice', r.status_code == 400 and coins_replay == coins_after, 'refused, no double credit', (r.status_code, coins_after, coins_replay), sev='P0')
        # --- after completion
        for label, resp in {
            'customer cannot cancel a completed booking': C.client.put('/customers/bookings/cancel/', {'booking_id': bid}, format='json'),
            'artist cannot cancel a completed booking': A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled'}, format='json'),
            'artist cannot re-confirm a completed booking': A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json'),
            'artist cannot mark a completed booking no-show': A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'no_show'}, format='json'),
        }.items():
            record(F, label, not is_2xx(resp) and Booking.objects.get(booking_id=bid).status.name == 'completed', 'refused', resp.status_code, sev='P0')
        r = C.client.post('/customers/reviews/create/', {'booking_id': bid, 'rating': 5, 'comment': 'great'}, format='json')
        prof = ArtistProfile.objects.get(artist_id=A.profile.artist_id)
        record(F, 'customer reviews the completed booking; artist rating updated', r.status_code == 201 and prof.total_reviews == 1 and prof.avg_rating == Decimal('5.00'), 'rated', (r.status_code, prof.total_reviews, prof.avg_rating), sev='P1')
        r = C.client.post('/customers/reviews/create/', {'booking_id': bid, 'rating': 1}, format='json')
        record(F, 'a booking can only be reviewed once (rating not double counted)', r.status_code == 400 and ArtistProfile.objects.get(artist_id=A.profile.artist_id).total_reviews == 1, 'refused', r.status_code, sev='P1')
        r = A.client.post('/artists/customer_reviews/create/', {'booking_id': bid, 'rating': 4}, format='json')
        record(F, 'artist rates the customer after completion', r.status_code == 201, 201, r.status_code, sev='P2')
        conv = Conversation.objects.filter(booking_id=bid).first()
        r = C.client.post('/chat/messages/create/', {'booking_id': bid, 'content': 'thanks'}, format='json')
        observe(F, 'chat after completion', f'conversation closed={getattr(conv, "status", None)}; new message HTTP {r.status_code}', sev='P3')

    def test_state_machine(self):
        A, C, B = self.art, self.cus, w.make_bookable_artist('+919700000010', 'SM Other Artist')

        def booking_in(state, day):
            bid = (data(w.create_booking(C, A, start='12:00:00', day=day)) or {}).get('booking_id')
            if state == 'confirmed':
                w.pay(bid); A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
            elif state in ('in_progress', 'completed', 'no_show'):
                w.pay(bid); A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
                Booking.objects.filter(booking_id=bid).update(status=__import__('sunndari_apps.core.models', fromlist=['BookingStatus']).BookingStatus.objects.get(name=state))
            elif state == 'declined':
                A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled', 'reason': 'busy'}, format='json')
            return bid

        def attempt(label, bid, resp, expect_status, sev='P0'):
            now = Booking.objects.get(booking_id=bid).status.name
            record('STATE-MACHINE', label, not is_2xx(resp) and now == expect_status, f'refused, stays {expect_status}', f'HTTP {resp.status_code}, now {now}', sev=sev)

        pin = lambda: 1234
        day = 4
        for state in ('declined', 'completed', 'no_show'):
            day += 1
            bid = booking_in(state, day)
            ds = 'cancelled' if state == 'declined' else state
            attempt(f'{state}: accept refused', bid, A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json'), ds)
            attempt(f'{state}: decline/cancel refused', bid, A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled'}, format='json'), ds)
            attempt(f'{state}: on-my-way refused', bid, A.client.put('/artists/bookings/on_my_way/', {'booking_id': bid}, format='json'), ds)
            attempt(f'{state}: arrived refused', bid, A.client.put('/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': 123456}, format='json'), ds)
            attempt(f'{state}: start PIN refused', bid, A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': 1234}, format='json'), ds)
            attempt(f'{state}: completion PIN refused', bid, A.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid, 'completion_pin': 1234}, format='json'), ds)
            attempt(f'{state}: customer cancel refused', bid, C.client.put('/customers/bookings/cancel/', {'booking_id': bid}, format='json'), ds)
        day += 1
        pending = booking_in('pending', day)
        attempt('pending: arrived refused', pending, A.client.put('/artists/bookings/arrived/', {'booking_id': pending, 'booking_otp': 123456}, format='json'), 'pending')
        attempt('pending: on-my-way refused', pending, A.client.put('/artists/bookings/on_my_way/', {'booking_id': pending}, format='json'), 'pending')
        attempt('pending: finish (completion PIN) refused', pending, A.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': pending, 'completion_pin': 1234}, format='json'), 'pending')
        attempt('pending: start PIN refused', pending, A.client.put('/artists/bookings/start_pin/verify/', {'booking_id': pending, 'start_service_pin': 1234}, format='json'), 'pending')
        for target in ('in_progress', 'completed', 'no_show'):
            attempt(f'pending: artist cannot jump straight to {target} through the status endpoint', pending, A.client.put('/artists/bookings/update_status/', {'booking_id': pending, 'status': target}, format='json'), 'pending')
        day += 1
        conf = booking_in('confirmed', day)
        for target in ('in_progress', 'completed'):
            attempt(f'confirmed: artist cannot jump to {target} without the PINs', conf, A.client.put('/artists/bookings/update_status/', {'booking_id': conf, 'status': target}, format='json'), 'confirmed')
        attempt('confirmed: other artist cannot cancel', conf, B.client.put('/artists/bookings/update_status/', {'booking_id': conf, 'status': 'cancelled'}, format='json'), 'confirmed')
        attempt('confirmed: customer cannot use the artist status endpoint', conf, C.client.put('/artists/bookings/update_status/', {'booking_id': conf, 'status': 'cancelled'}, format='json'), 'confirmed')
        r = A.client.put('/artists/bookings/update_status/', {'booking_id': conf, 'status': 'banana'}, format='json')
        record('STATE-MACHINE', 'unknown status value -> controlled 400', r.status_code == 400, 400, r.status_code, sev='P2')
        # in_progress: cancellation policy
        day += 1
        prog = booking_in('in_progress', day)
        attempt('in_progress: artist cannot cancel mid-service', prog, A.client.put('/artists/bookings/update_status/', {'booking_id': prog, 'status': 'cancelled'}, format='json'), 'in_progress')
        r = C.client.put('/customers/bookings/cancel/', {'booking_id': prog}, format='json')
        record('STATE-MACHINE', 'customer cannot cancel (and be refunded) while the service is already in progress', not is_2xx(r) and Booking.objects.get(booking_id=prog).status.name == 'in_progress', 'refused',
               f'HTTP {r.status_code}, booking now {Booking.objects.get(booking_id=prog).status.name}', sev='P1',
               note='customers/views/booking.py:cancel_extract allows any ACTIVE status, which includes in_progress; the payment is marked refunded')

    def test_self_booking_and_duplicates(self):
        A = self.art
        # an artist acting as a customer on their own services
        mine = A.client.post('/customers/bookings/create/', {
            'artist_id': A.profile.artist_id, 'package_id': A.package.package_id, 'location_type_id': w.location('Studio').location_type_id,
            'booking_date': w.fmt_date(w.future_date(9)), 'start_time': '10:00:00'}, format='json')
        record('BUSINESS-LOGIC', 'an artist cannot book their own services (self-booking / fake-review / cashback abuse)', not is_2xx(mine), 'refused', f'HTTP {mine.status_code}', sev='P1',
               note='create_booking has no role or self-ownership check; completing a self-booking pays cashback and allows a self-review')
        if is_2xx(mine):
            bid = data(mine)['booking_id']
            w.pay(bid)
            A.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
        # duplicates
        C = self.cus
        r1 = w.create_booking(C, A, start='15:00:00', day=10)
        r2 = w.create_booking(C, A, start='15:00:00', day=10)
        other = w.make_customer('+919700000020', 'Dup Customer')
        r3 = w.create_booking(other, A, start='15:30:00', day=10)
        record('BOOKING', 'same slot twice (retry/duplicate request) -> second refused', r1.status_code == 201 and r2.status_code == 400, '201 then 400', (r1.status_code, r2.status_code), sev='P0')
        record('BOOKING', 'a different customer cannot take an overlapping slot', r3.status_code == 400, 400, r3.status_code, sev='P0')
        n = Booking.objects.filter(artist=A.profile, booking_date=w.future_date(10)).count()
        record('BOOKING', 'exactly one booking exists for the contested slot', n == 1, 1, n, sev='P0')
        # booking guards
        cases = {
            'past date': dict(day=-1), 'artist not approved': None,
        }
        r = w.create_booking(C, A, day=-1)
        record('BOOKING', 'booking in the past refused', r.status_code == 400, 400, r.status_code, sev='P1')
        t = (timezone.now().astimezone(IST) + datetime.timedelta(minutes=30))
        r = C.client.post('/customers/bookings/create/', {'artist_id': A.profile.artist_id, 'package_id': A.package.package_id, 'location_type_id': w.location('Studio').location_type_id,
                                                         'booking_date': t.strftime('%d-%m-%y'), 'start_time': t.strftime('%H:%M:%S')}, format='json')
        record('BOOKING', 'booking less than 2 hours ahead refused', r.status_code == 400, 400, r.status_code, sev='P1')
        ArtistAvailabilityBlock.objects.create(artist=A.profile, block_date=w.future_date(11))
        record('BOOKING', 'booking on a blocked date refused', w.create_booking(C, A, day=11).status_code == 400, 400, 'checked', sev='P0')
        record('BOOKING', 'booking outside working hours refused (05:00 and 21:30+1h)', w.create_booking(C, A, start='05:00:00', day=12).status_code == 400 and w.create_booking(C, A, start='21:30:00', day=12).status_code == 400, 'both refused', 'checked', sev='P0')
        ArtistServiceArea.objects.create(artist=A.profile, city='Delhi', travel_charge_type='free')
        record('BOOKING', 'home visit outside the artist service areas refused', w.create_booking(C, A, start='11:00:00', day=13).status_code == 400, 400, 'checked', sev='P0')
        record('BOOKING', 'home visit without an address refused once areas are configured', w.create_booking(C, A, start='11:00:00', day=13, address=False).status_code == 400, 400, 'checked', sev='P1')
        ArtistServiceArea.objects.filter(artist=A.profile).delete()
        B = w.make_bookable_artist('+919700000030', 'Foreign pkg artist')
        r = C.client.post('/customers/bookings/create/', {'artist_id': A.profile.artist_id, 'package_id': B.package.package_id, 'location_type_id': w.location('Studio').location_type_id,
                                                         'booking_date': w.fmt_date(w.future_date(14)), 'start_time': '10:00:00'}, format='json')
        record('BOOKING', "another artist's package cannot be booked under this artist", r.status_code == 400, 400, r.status_code, sev='P0')
        foreign_addr = w.make_customer('+919700000031', 'Addr Owner').address.address_id
        r = C.client.post('/customers/bookings/create/', {'artist_id': A.profile.artist_id, 'package_id': A.package.package_id, 'location_type_id': w.location('Home Visit').location_type_id,
                                                         'address_id': foreign_addr, 'booking_date': w.fmt_date(w.future_date(14)), 'start_time': '10:00:00'}, format='json')
        record('BOOKING', "another customer's address cannot be used", r.status_code == 400, 400, r.status_code, sev='P0')
        unapproved = w.make_bookable_artist('+919700000032', 'Unapproved', approved=False)
        r = C.client.post('/customers/bookings/create/', {'artist_id': unapproved.profile.artist_id, 'package_id': unapproved.package.package_id, 'location_type_id': w.location('Studio').location_type_id,
                                                         'booking_date': w.fmt_date(w.future_date(14)), 'start_time': '10:00:00'}, format='json')
        record('BOOKING', 'unapproved artist cannot be booked', r.status_code == 400, 400, r.status_code, sev='P0')
        PricingPackage = __import__('sunndari_apps.artists.models', fromlist=['PricingPackage']).PricingPackage
        PricingPackage.objects.filter(package_id=A.package.package_id).update(is_active=False)
        record('BOOKING', 'inactive package cannot be booked', w.create_booking(C, A, day=15).status_code == 400, 400, 'checked', sev='P1')
        PricingPackage.objects.filter(package_id=A.package.package_id).update(is_active=True)
        r = C.client.post('/customers/bookings/create/', {'artist_id': A.profile.artist_id, 'package_id': A.package.package_id, 'location_type_id': w.location('Studio').location_type_id,
                                                         'booking_date': w.fmt_date(w.future_date(15)), 'start_time': '10:00:00', 'total_amount': '1', 'travel_fee': '0', 'platform_fee': '0', 'status': 'confirmed'}, format='json')
        b = Booking.objects.get(booking_id=data(r)['booking_id'])
        record('BOOKING', 'client-supplied price/status fields are ignored', b.total_amount == Decimal('2000.00') and b.status.name == 'pending', '2000 / pending', (b.total_amount, b.status.name), sev='P0')
        unverified('CONCURRENCY', 'two customers booking the same artist/slot at the same instant',
                   'Cannot be exercised here (SQLite test DB serialises writers). Since the Q-06 fix, validate_slot() first locks the artist ProfileRow (select_for_update) so concurrent bookings for one artist queue up on PostgreSQL; this is asserted by a unit test (lock order) but the actual two-connection race still needs a PostgreSQL concurrency test. There is still no DB-level exclusion constraint.', sev='P2')
