"""End-to-end flows for artist salon addresses and In-Salon bookings, through the real HTTP endpoints.

Everything about the salon goes through the API (add, list, edit, delete, the customer's artist page, booking,
booking responses). The booking is paid through the real initiate/verify endpoints with Razorpay faked; the only
direct database touches are the ones the existing lifecycle test also makes (reading nothing secret, and moving the
appointment time closer so the "on my way" window opens).

What it holds together:
  * the salon a customer chose is saved on the booking and every booking response keeps showing exactly that salon,
    at every stage (pending, paid, confirmed, on my way, arrived, in progress, completed, cancelled), no matter what
    the artist later does to the address (edit, delete);
  * an artist can change or delete addresses freely without touching a single booking;
  * the booking-type rules (Home Visit / On-Site Event / In-Salon) hold from the customer's side;
  * an unexpected ERROR log fails the test, so a swallowed exception cannot hide behind a green run.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.db import connection
from django.db.models import RestrictedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistAvailabilitySchedule, ArtistSalonAddress
from sunndari_apps.core.models import LocationType
from sunndari_apps.customers.models import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.wallet.models import CoinConfig, CoinTransaction, CustomerWallet
from tests.booking_address import address_for
from tests.test_customers import (
    IST, make_artist, make_customer, make_location_type, make_package, make_sub_category, seed_booking_statuses,
    seed_payment_statuses,
)

CREATE = '/artists/salon_addresses/create/'
LIST = '/artists/salon_addresses/get_all/'
UPDATE = '/artists/salon_addresses/update/'
DELETE = '/artists/salon_addresses/delete/'
BOOK = '/customers/bookings/create/'
EXPECTED_NOISE = ('Firestore', 'Firebase')


class _ErrorCollector(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class SalonLifecycleBase(TestCase):

    def setUp(self):
        CoinConfig.objects.create(coin_value_rupees='0.10')
        seed_booking_statuses()
        seed_payment_statuses()
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        client = patcher.start()
        self.addCleanup(patcher.stop)
        self.gateway = MagicMock()
        self.gateway.order.create.side_effect = lambda data: {
            'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': data['currency'], 'status': 'created',
        }
        self.gateway.utility.verify_payment_signature.return_value = None
        client.return_value = self.gateway

        self.errors = _ErrorCollector()
        logging.getLogger().addHandler(self.errors)
        self.addCleanup(logging.getLogger().removeHandler, self.errors)

        self.customer_client, self.customer = make_customer(phone_number='+919800070001')
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919800070002')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=30)
        self.salon_type = make_location_type(LocationType.IN_SALON)
        self.home_type = make_location_type(LocationType.HOME_VISIT)
        self.event_type = make_location_type(LocationType.ON_SITE_EVENT)
        for location_type in (self.salon_type, self.home_type, self.event_type):
            resp = self.artist_client.post('/artists/locations/add/',
                                           {'location_type_id': location_type.location_type_id}, format='json')
            self.assertEqual(resp.status_code, 201, resp.content)
        # Open every day all day, so any start time we pick is inside the working window.
        for day in range(7):
            ArtistAvailabilitySchedule.objects.create(
                artist=self.profile, day_of_week=day, start_time='00:00:00', end_time='23:59:00')

    def tearDown(self):
        real = [r for r in self.errors.records if not any(n in r.getMessage() for n in EXPECTED_NOISE)]
        self.assertEqual(real, [], [r.getMessage() for r in real])

    # -- helpers ---------------------------------------------------------------------------------------------------
    def add_salon(self, name, **overrides):
        body = {'name': name, 'address_line_1': f'{name} Road', 'city': 'Lucknow', 'pin_code': '226010',
                'latitude': '26.846694', 'longitude': '80.946166'}
        body.update(overrides)
        resp = self.artist_client.post(CREATE, body, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()['data']['salon_address_id']

    def page_salons(self):
        resp = self.customer_client.get('/customers/artists/get/', {'artist_id': self.profile.artist_id})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()['data']['salonAddresses']

    def start_at(self, hours_ahead=3, extra_days=0):
        return (timezone.now() + timedelta(hours=hours_ahead, days=extra_days)).astimezone(IST)

    def book(self, location_type, when, client=None, **extra):
        body = {'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
                'location_type_id': location_type.location_type_id,
                'booking_date': when.strftime('%d-%m-%y'), 'start_time': when.strftime('%H:%M:%S')}
        body.update(extra)
        return (client or self.customer_client).post(BOOK, body, format='json')

    def pay(self, booking_id):
        init = self.customer_client.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json')
        self.assertEqual(init.status_code, 201, init.content)
        order_id, paise = init.data['data']['gateway_order_id'], init.data['data']['amount']
        self.gateway.payment.fetch.return_value = {'id': 'pay_salon', 'order_id': order_id, 'status': 'captured', 'amount': paise}
        self.gateway.order.fetch.return_value = {'id': order_id, 'amount': paise, 'amount_paid': paise, 'amount_due': 0,
                                                'currency': 'INR', 'status': 'paid'}
        verify = self.customer_client.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_salon', 'razorpay_signature': 'ok'}, format='json')
        self.assertEqual(verify.status_code, 200, verify.content)

    def customer_view(self, booking_id):
        resp = self.customer_client.get('/customers/bookings/get/', {'booking_id': booking_id})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()['data']

    def artist_view(self, booking_id):
        resp = self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()['data']

    def assert_both_see(self, booking_id, expected):
        for view in (self.customer_view, self.artist_view):
            data = view(booking_id)
            self.assertEqual(data['salonAddress'], expected, view.__name__)
            self.assertIsNone(data['address'])
            self.assertEqual(data['travelFee'], '0.00')


class SalonFullLifecycleTest(SalonLifecycleBase):

    def test_in_salon_booking_from_salon_setup_to_completion_with_the_address_changing_underneath(self):
        # ── The artist sets up two salons and tidies one ───────────────────────────────────────────────────────
        first = self.add_salon('Gomti Nagar Studio', address_line_2='Near Metro Pillar 120')
        second = self.add_salon('Hazratganj Studio', latitude='26.85', longitude='80.94')
        junk = self.add_salon('Old Test Entry')
        self.assertEqual(self.artist_client.delete(f'{DELETE}?salon_address_id={junk}').status_code, 200)
        listed = self.artist_client.get(LIST).json()['data']
        self.assertEqual([row['salon_address_id'] for row in listed], [first, second])
        self.assertEqual(self.artist_client.put(UPDATE, {'salon_address_id': second, 'pin_code': '226001'},
                                                format='json').status_code, 200)

        # ── The customer sees exactly the two live salons on the artist page ────────────────────────────────────
        offered = self.page_salons()
        self.assertEqual([s['salonAddressId'] for s in offered], [first, second])
        chosen = next(s for s in offered if s['salonAddressId'] == first)

        # ── Booking: the salon is required and nothing is chosen for the customer ───────────────────────────
        when = self.start_at(3)
        refused = self.book(self.salon_type, when)
        self.assertEqual(refused.status_code, 400)
        self.assertIn(Constants.salon_address_required, refused.json()['message'])
        response = self.book(self.salon_type, when, salon_address_id=first)
        self.assertEqual(response.status_code, 201, response.content)
        booking_id = response.data['data']['booking_id']
        self.assertEqual(response.data['data']['travel_fee'], '0.00')
        self.assertEqual(response.data['data']['total_amount'], '1500.00')
        self.assertEqual((chosen['latitude'], chosen['longitude']), (26.846694, 80.946166))
        self.assertEqual((chosen['name'], chosen['city'], chosen['addressLine2']), ('Gomti Nagar Studio', 'Lucknow', 'Near Metro Pillar 120'))

        # The customer sees it at once; the artist only once it is paid.
        self.assertEqual(self.customer_view(booking_id)['salonAddress'], chosen)
        self.pay(booking_id)
        self.assert_both_see(booking_id, chosen)

        # ── The artist accepts ─────────────────────────────────────────────────────────────────────────────────
        accept = self.artist_client.put('/artists/bookings/update_status/',
                                        {'booking_id': booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(accept.status_code, 200, accept.content)
        self.assert_both_see(booking_id, chosen)

        # ── Meanwhile the artist renames, moves and finally deletes that very salon ────────────────────────
        self.assertEqual(self.artist_client.put(UPDATE, {
            'salon_address_id': first, 'name': 'Renamed Studio', 'city': 'Kanpur',
            'latitude': '1.5', 'longitude': '2.5'}, format='json').status_code, 200)
        self.assert_both_see(booking_id, chosen)                       # booking unchanged by the edit
        self.assertEqual(self.artist_client.delete(f'{DELETE}?salon_address_id={first}').status_code, 200)
        self.assert_both_see(booking_id, chosen)                       # ... and by the delete
        self.assertEqual([s['salonAddressId'] for s in self.page_salons()], [second])
        self.assertEqual(self.artist_client.get(LIST).json()['data'][0]['salon_address_id'], second)
        late = self.book(self.salon_type, self.start_at(6), salon_address_id=first)
        self.assertEqual(late.status_code, 400)                        # a deleted salon can no longer be chosen
        self.assertIn(Constants.salon_address_unavailable, late.json()['message'])

        # ── The service itself, step by step; the salon is the same at every stage ────────────────────────
        booking = Booking.objects.get(booking_id=booking_id)
        near = self.start_at(1)
        booking.booking_date, booking.start_time = near.date(), near.time()
        booking.save()
        self.assertEqual(self.artist_client.put('/artists/bookings/on_my_way/', {'booking_id': booking_id},
                                                format='json').status_code, 200)
        self.assert_both_see(booking_id, chosen)
        self.assertEqual(self.artist_client.put('/artists/bookings/arrived/', {'booking_id': booking_id},
                                                format='json').status_code, 200)
        self.assert_both_see(booking_id, chosen)
        pin = self.customer_client.get('/customers/bookings/start_pin/', {'booking_id': booking_id}).data['data']['startServicePin']
        self.assertEqual(self.artist_client.put('/artists/bookings/start_pin/verify/', {
            'booking_id': booking_id, 'start_service_pin': pin}, format='json').status_code, 200)
        self.assert_both_see(booking_id, chosen)
        self.assertEqual(self.artist_client.put('/artists/bookings/completion_pin/request/', {'booking_id': booking_id},
                                                format='json').status_code, 200)
        pin = self.customer_client.get('/customers/bookings/completion_pin/', {'booking_id': booking_id}).data['data']['completionPin']
        done = self.artist_client.put('/artists/bookings/completion_pin/verify/', {
            'booking_id': booking_id, 'completion_pin': pin}, format='json')
        self.assertEqual(done.status_code, 200, done.content)
        self.assert_both_see(booking_id, chosen)

        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'completed')
        self.assertEqual(booking.salon_address_id, first)
        self.assertIsNone(booking.address_id)
        self.assertEqual(CustomerWallet.objects.get(customer_id=self.customer.user_id).balance_coins, 15)
        self.assertTrue(Notification.objects.filter(booking_id=booking_id, type='booking_completed').exists())

        # ── Lists show it too, and the deleted salon row is still there, just switched off ────────────────
        rows = self.customer_client.get('/customers/bookings/get_all/').json()['data']['data']
        self.assertEqual(rows[0]['salonAddress'], chosen)
        rows = self.artist_client.get('/artists/bookings/get_all/').json()['data']['data']
        self.assertEqual(rows[0]['salonAddress'], chosen)
        kept = ArtistSalonAddress.objects.get(pk=first)
        self.assertFalse(kept.is_active)
        with self.assertRaises(RestrictedError):
            kept.delete()                                              # history cannot be erased from under a booking

    def test_cancelled_in_salon_booking_keeps_its_salon_and_the_salon_can_then_be_deleted(self):
        salon = self.add_salon('Studio')
        chosen = self.page_salons()[0]
        booking_id = self.book(self.salon_type, self.start_at(48), salon_address_id=salon).data['data']['booking_id']
        self.pay(booking_id)
        cancel = self.customer_client.put('/customers/bookings/cancel/', {'booking_id': booking_id, 'reason': 'Change of plans'}, format='json')
        self.assertEqual(cancel.status_code, 200, cancel.content)
        self.assertEqual(Booking.objects.get(booking_id=booking_id).status.name, 'cancelled')
        self.assert_both_see(booking_id, chosen)
        self.assertEqual(self.artist_client.delete(f'{DELETE}?salon_address_id={salon}').status_code, 200)
        self.assert_both_see(booking_id, chosen)

    def test_rescheduled_in_salon_booking_keeps_its_salon(self):
        salon = self.add_salon('Studio')
        chosen = self.page_salons()[0]
        booking_id = self.book(self.salon_type, self.start_at(48), salon_address_id=salon).data['data']['booking_id']
        self.pay(booking_id)
        self.artist_client.put('/artists/bookings/update_status/', {'booking_id': booking_id, 'status': 'confirmed'}, format='json')
        new_day = self.start_at(72)
        request = self.artist_client.post('/artists/bookings/reschedule/request/', {
            'booking_id': booking_id, 'proposed_date': new_day.strftime('%d-%m-%y'),
            'proposed_start_time': new_day.strftime('%H:%M:%S'), 'reason': 'Running late'}, format='json')
        self.assertEqual(request.status_code, 201, request.content)
        accepted = self.customer_client.put('/customers/bookings/reschedule/respond/', {
            'reschedule_id': request.data['data']['reschedule_id'], 'decision': 'accepted'}, format='json')
        self.assertEqual(accepted.status_code, 200, accepted.content)
        booking = Booking.objects.get(booking_id=booking_id)
        self.assertEqual(booking.booking_date, new_day.date())
        self.assert_both_see(booking_id, chosen)

    def test_one_customer_books_all_three_types_and_each_response_is_right(self):
        salon = self.add_salon('Studio')
        chosen = self.page_salons()[0]
        in_salon = self.book(self.salon_type, self.start_at(30), salon_address_id=salon).data['data']['booking_id']
        home = self.book(self.home_type, self.start_at(34), **address_for(self.customer_client)).data['data']['booking_id']
        event = self.book(self.event_type, self.start_at(38), **address_for(self.customer_client)).data['data']['booking_id']
        self.assertEqual(self.customer_view(in_salon)['salonAddress'], chosen)
        for booking_id in (home, event):
            data = self.customer_view(booking_id)
            self.assertIsNone(data['salonAddress'])
            self.assertIsNotNone(data['address'])
        rows = {r['bookingId']: r for r in self.customer_client.get('/customers/bookings/get_all/').json()['data']['data']}
        self.assertEqual(rows[in_salon]['salonAddress'], chosen)
        self.assertIsNone(rows[home]['salonAddress'])
        self.assertIsNone(rows[event]['salonAddress'])

    def test_salon_booking_alongside_an_artists_other_work_does_not_disturb_neighbouring_slots(self):
        # In-Salon has no travel or return buffer: an appointment right after it is bookable.
        salon = self.add_salon('Studio')
        first = self.start_at(30).replace(minute=0, second=0, microsecond=0)
        self.assertEqual(self.book(self.salon_type, first, salon_address_id=salon).status_code, 201)
        second = self.book(self.salon_type, first + timedelta(minutes=30), salon_address_id=salon)
        self.assertEqual(second.status_code, 201, second.content)
        clash = self.book(self.salon_type, first + timedelta(minutes=15), salon_address_id=salon)
        # (an unpaid pending booking holds no slot, so the clash only shows once the first is paid)
        self.pay(Booking.objects.order_by('booking_id').first().booking_id)
        clash = self.book(self.salon_type, first + timedelta(minutes=15), salon_address_id=salon)
        self.assertEqual(clash.status_code, 400)


class SalonLogicChecksTest(SalonLifecycleBase):
    """Edge cases and the real blockers around the feature."""

    def test_an_artist_with_in_salon_on_but_no_salon_address_cannot_be_booked_in_salon_and_says_why(self):
        # The page shows no salons, so an app can hide the In-Salon choice; a direct call is refused with a clear text.
        self.assertEqual(self.page_salons(), [])
        response = self.book(self.salon_type, self.start_at(30))
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_required, response.json()['message'])
        self.assertEqual(Booking.objects.count(), 0)

    def test_deleting_the_last_salon_stops_new_in_salon_bookings_but_not_existing_ones(self):
        salon = self.add_salon('Only Studio')
        existing = self.book(self.salon_type, self.start_at(30), salon_address_id=salon).data['data']['booking_id']
        self.pay(existing)
        self.artist_client.delete(f'{DELETE}?salon_address_id={salon}')
        self.assertEqual(self.page_salons(), [])
        refused = self.book(self.salon_type, self.start_at(40), salon_address_id=salon)
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(self.customer_view(existing)['salonAddress']['name'], 'Only Studio')
        # The artist can add a new one and bookings resume.
        again = self.add_salon('Only Studio')                           # the freed name is reusable
        self.assertEqual(self.book(self.salon_type, self.start_at(40), salon_address_id=again).status_code, 201)

    def test_another_artists_salon_cannot_be_used_even_when_its_id_is_known(self):
        _, _, other = make_artist(phone_number='+919800070003')
        theirs = ArtistSalonAddress().create(artist_id=other.artist_id, name='Theirs', address_line_1='1 Road',
                                             city='Delhi', pin_code='110001', latitude=Decimal('28.6'), longitude=Decimal('77.2'))
        mine = self.add_salon('Mine')
        response = self.book(self.salon_type, self.start_at(30), salon_address_id=theirs)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_unavailable, response.json()['message'])
        self.assertEqual(self.book(self.salon_type, self.start_at(30), salon_address_id=mine).status_code, 201)

    def test_a_customer_cannot_use_an_address_edit_endpoint_and_an_artist_cannot_book_themselves(self):
        salon = self.add_salon('Mine')
        for call in (lambda: self.customer_client.post(CREATE, {'name': 'x'}, format='json'),
                     lambda: self.customer_client.put(UPDATE, {'salon_address_id': salon, 'name': 'x'}, format='json'),
                     lambda: self.customer_client.delete(f'{DELETE}?salon_address_id={salon}')):
            self.assertEqual(call().status_code, 400)
        self.assertEqual(ArtistSalonAddress.objects.get(pk=salon).name, 'Mine')
        self_booking = self.book(self.salon_type, self.start_at(30), client=self.artist_client, salon_address_id=salon)
        self.assertEqual(self_booking.status_code, 400)

    def test_switched_off_artist_exposes_no_salons_and_takes_no_in_salon_bookings(self):
        salon = self.add_salon('Studio')
        self.artist_client.put('/artists/profile/accepting_bookings/', {'is_accepting_bookings': False}, format='json')
        page = self.customer_client.get('/customers/artists/get/', {'artist_id': self.profile.artist_id})
        self.assertEqual(page.status_code, 400)
        self.assertNotIn('Studio', page.content.decode())
        response = self.book(self.salon_type, self.start_at(30), salon_address_id=salon)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_every_booking_reading_endpoint_copes_with_an_in_salon_booking_that_has_no_home_address(self):
        # A booking without a customer address must not break anything that reads bookings.
        salon = self.add_salon('Studio')
        booking_id = self.book(self.salon_type, self.start_at(30), salon_address_id=salon).data['data']['booking_id']
        self.pay(booking_id)
        calls = [
            (self.customer_client, '/customers/bookings/get/', {'booking_id': booking_id}),
            (self.customer_client, '/customers/bookings/get_all/', {}),
            (self.customer_client, '/customers/bookings/get_all/', {'filter_key': 'paymentStatus', 'filter_value': 'paid'}),
            (self.customer_client, '/customers/bookings/get_all/', {'search_key': 'Studio'}),
            (self.artist_client, '/artists/bookings/get/', {'booking_id': booking_id}),
            (self.artist_client, '/artists/bookings/get_all/', {}),
            (self.artist_client, '/artists/clients/get_all/', {}),
            (self.artist_client, '/artists/insights/summary/', {}),
            (self.customer_client, '/customers/artists/availability/', {
                'artist_id': self.profile.artist_id, 'booking_date': self.start_at(30).strftime('%d-%m-%y')}),
        ]
        for client, url, query in calls:
            response = client.get(url, query)
            self.assertLess(response.status_code, 500, (url, response.content))
            self.assertEqual(response.status_code, 200, (url, response.content))

    def test_booking_lists_do_not_get_slower_with_more_in_salon_bookings(self):
        salon = self.add_salon('Studio')

        def queries(url, client):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(client.get(url).status_code, 200)
            return len(ctx)

        self.pay(self.book(self.salon_type, self.start_at(30), salon_address_id=salon).data['data']['booking_id'])
        few = (queries('/customers/bookings/get_all/', self.customer_client), queries('/artists/bookings/get_all/', self.artist_client))
        for i in range(8):
            self.pay(self.book(self.salon_type, self.start_at(40 + i * 2), salon_address_id=salon).data['data']['booking_id'])
        many = (queries('/customers/bookings/get_all/', self.customer_client), queries('/artists/bookings/get_all/', self.artist_client))
        self.assertEqual(few, many)                                    # same number of queries for 1 or 9 bookings

    def test_the_ten_address_limit_and_a_full_book_of_salons_on_the_page(self):
        ids = [self.add_salon(f'Studio {i}') for i in range(10)]
        over = self.artist_client.post(CREATE, {
            'name': 'One too many', 'address_line_1': 'x', 'city': 'x', 'pin_code': '1',
            'latitude': '1', 'longitude': '1'}, format='json')
        self.assertEqual(over.status_code, 400)
        self.assertEqual([s['salonAddressId'] for s in self.page_salons()], ids)
        self.artist_client.delete(f'{DELETE}?salon_address_id={ids[0]}')
        self.add_salon('Studio 0')                                      # a freed slot and a freed name
        self.assertEqual(len(self.page_salons()), 10)

    def test_salons_of_two_artists_stay_separate_through_the_whole_flow(self):
        other_client, _, other = make_artist(phone_number='+919800070004')
        make_package(other, sub_category=make_sub_category(), price=1000, duration=30)
        other_client.post('/artists/locations/add/', {'location_type_id': self.salon_type.location_type_id}, format='json')
        other_client.post(CREATE, {'name': 'Studio', 'address_line_1': 'Delhi Road', 'city': 'Delhi', 'pin_code': '110001',
                                   'latitude': '28.6', 'longitude': '77.2'}, format='json')
        mine = self.add_salon('Studio')                                 # same name as the other artist's: allowed
        self.assertEqual(len(self.artist_client.get(LIST).json()['data']), 1)
        self.assertEqual(len(other_client.get(LIST).json()['data']), 1)
        self.assertEqual(self.artist_client.get(LIST).json()['data'][0]['salon_address_id'], mine)
        self.assertEqual([s['city'] for s in self.page_salons()], ['Lucknow'])
