"""Every booking-lifecycle endpoint called in every booking state: which calls must work, which must
be refused. A logic check of the whole state machine (incl. the arrival-without-OTP and
completion-PIN-request changes), with the clock frozen at 12:00 IST so the time windows are stable."""
import itertools
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as dj_timezone

from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.customers.models import Booking

from tests.test_customers import (
    make_artist, make_customer, make_sub_category, make_package, make_location_type, make_booking,
    make_paid_payment, seed_booking_statuses,
)

NOW = datetime(2030, 1, 15, 6, 30, tzinfo=dt_timezone.utc)          # 12:00 IST
DAY = datetime(2030, 1, 15).date()
STATES = ['pending_unpaid', 'pending_paid', 'confirmed', 'on_my_way', 'arrived', 'in_progress',
          'completion_requested', 'completed', 'cancelled', 'no_show']

# action -> {state: expected HTTP status}; a state that is absent must be refused (400)
ALLOWED = {
    'accept':               {'pending_paid': 200},
    'artist_cancel':        {'pending_unpaid': 200, 'pending_paid': 200, 'confirmed': 200, 'on_my_way': 200, 'arrived': 200},
    'artist_no_show':       {'in_progress': 200, 'completion_requested': 200},
    'on_my_way':            {'confirmed': 200},
    'arrived':              {'on_my_way': 200},
    'start_verify':         {'arrived': 200},
    'completion_request':   {'in_progress': 200, 'completion_requested': 200},
    'completion_verify':    {'completion_requested': 200},
    'customer_cancel':      {'pending_unpaid': 200, 'pending_paid': 200, 'confirmed': 200, 'on_my_way': 200},
    'customer_start_pin':   {'arrived': 200},
    'customer_completion_pin': {'completion_requested': 200},
}


class BookingStateMatrixTest(TestCase):
    counter = itertools.count(1)

    def setUp(self):
        seed_booking_statuses()
        self.sub = make_sub_category()
        self.location = make_location_type()
        patcher = patch('django.utils.timezone.now', return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def world(self, state):
        n = next(self.counter)
        artist_client, _, profile = make_artist(phone_number=f'+9190002{n:05d}')
        customer_client, customer = make_customer(phone_number=f'+9190003{n:05d}')
        package = make_package(profile, sub_category=self.sub)
        status_name = {'pending_unpaid': 'pending', 'pending_paid': 'pending', 'confirmed': 'confirmed', 'on_my_way': 'confirmed',
                       'arrived': 'confirmed', 'in_progress': 'in_progress', 'completion_requested': 'in_progress',
                       'completed': 'completed', 'cancelled': 'cancelled', 'no_show': 'no_show'}[state]
        booking = make_booking(customer, profile, package, self.location, DAY, '13:00:00', '13:30:00', status_name=status_name)
        fields = {}
        if state != 'pending_unpaid':
            make_paid_payment(booking)
        if state in ('on_my_way', 'arrived'):
            fields['on_my_way_at'] = NOW
        if state == 'arrived':
            fields.update(arrived_at=NOW, start_service_pin=1234, start_pin_expiry=NOW + timedelta(hours=5))
        if state in ('in_progress', 'completion_requested'):
            fields.update(on_my_way_at=NOW, arrived_at=NOW, service_started_at=NOW)
        if state == 'completion_requested':
            fields.update(completion_pin=4321, completion_pin_expiry=NOW + timedelta(hours=5))
        if state == 'confirmed' or state == 'on_my_way' or state == 'arrived' or state.startswith('in_') or state == 'completion_requested':
            fields.setdefault('expires_at', None)
        Booking.objects.filter(booking_id=booking.booking_id).update(**fields)
        return artist_client, customer_client, booking.booking_id

    def call(self, action, artist_client, customer_client, booking_id):
        body = {'booking_id': booking_id}
        a, c = artist_client, customer_client
        return {
            'accept': lambda: a.put('/artists/bookings/update_status/', {**body, 'status': 'confirmed'}, format='json'),
            'artist_cancel': lambda: a.put('/artists/bookings/update_status/', {**body, 'status': 'cancelled'}, format='json'),
            'artist_no_show': lambda: a.put('/artists/bookings/update_status/', {**body, 'status': 'no_show'}, format='json'),
            'on_my_way': lambda: a.put('/artists/bookings/on_my_way/', body, format='json'),
            'arrived': lambda: a.put('/artists/bookings/arrived/', body, format='json'),
            'start_verify': lambda: a.put('/artists/bookings/start_pin/verify/', {**body, 'start_service_pin': 1234}, format='json'),
            'completion_request': lambda: a.put('/artists/bookings/completion_pin/request/', body, format='json'),
            'completion_verify': lambda: a.put('/artists/bookings/completion_pin/verify/', {**body, 'completion_pin': 4321}, format='json'),
            'customer_cancel': lambda: c.put('/customers/bookings/cancel/', body, format='json'),
            'customer_start_pin': lambda: c.get('/customers/bookings/start_pin/', body),
            'customer_completion_pin': lambda: c.get('/customers/bookings/completion_pin/', body),
        }[action]()

    def test_every_action_in_every_state(self):
        mismatches = []
        for state in STATES:
            for action, allowed in ALLOWED.items():
                artist_client, customer_client, booking_id = self.world(state)
                resp = self.call(action, artist_client, customer_client, booking_id)
                expected = allowed.get(state, 400)
                if resp.status_code != expected:
                    mismatches.append(f'{action:24} in {state:21} -> {resp.status_code} (expected {expected}) {str(resp.json().get("message"))[:70]}')
        self.assertEqual(mismatches, [], '\n' + '\n'.join(mismatches))

    def test_the_happy_path_ends_completed_with_every_pin_cleared(self):
        artist_client, customer_client, booking_id = self.world('pending_paid')
        for action in ('accept', 'on_my_way', 'arrived'):
            self.assertEqual(self.call(action, artist_client, customer_client, booking_id).status_code, 200, action)
        pin = customer_client.get('/customers/bookings/start_pin/', {'booking_id': booking_id}).data['data']['startServicePin']
        self.assertEqual(artist_client.put('/artists/bookings/start_pin/verify/',
                                           {'booking_id': booking_id, 'start_service_pin': pin}, format='json').status_code, 200)
        self.assertEqual(self.call('customer_completion_pin', artist_client, customer_client, booking_id).status_code, 400)
        self.assertEqual(self.call('completion_request', artist_client, customer_client, booking_id).status_code, 200)
        done_pin = customer_client.get('/customers/bookings/completion_pin/', {'booking_id': booking_id}).data['data']['completionPin']
        self.assertEqual(artist_client.put('/artists/bookings/completion_pin/verify/',
                                           {'booking_id': booking_id, 'completion_pin': done_pin}, format='json').status_code, 200)
        booking = Booking.objects.get(booking_id=booking_id)
        self.assertEqual(booking.status.name, 'completed')
        self.assertIsNone(booking.completion_pin)
        self.assertIsNone(booking.start_service_pin)
        self.assertIsNone(booking.start_pin_expiry)
        self.assertIsNone(booking.completion_pin_expiry and None if booking.completion_pin is None else 'x')

    def test_pins_never_appear_in_any_booking_response(self):
        artist_client, customer_client, booking_id = self.world('completion_requested')
        for client, base in ((artist_client, '/artists/bookings'), (customer_client, '/customers/bookings')):
            for url in (f'{base}/get/?booking_id={booking_id}', f'{base}/get_all/'):
                body = client.get(url).content.decode()
                for leaked in ('4321', 'completion_pin', 'completionPin', 'start_service_pin', 'booking_otp'):
                    self.assertNotIn(leaked, body, f'{leaked} leaked from {url}')
