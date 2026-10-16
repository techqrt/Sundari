"""Completion PIN is issued when the artist taps "Complete service", not when the service starts."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from sunndari_apps.customers.models import Booking
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import (
    make_artist, make_customer, make_sub_category, make_package, make_location_type, make_booking, next_weekday,
)

REQUEST = '/artists/bookings/completion_pin/request/'
VERIFY = '/artists/bookings/completion_pin/verify/'
CUSTOMER_GET = '/customers/bookings/completion_pin/'


class RequestCompletionPinTest(TestCase):
    def setUp(self):
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000007001')
        self.customer_client, self.customer = make_customer(phone_number='+919000007002')
        package = make_package(self.profile, sub_category=make_sub_category())
        self.booking = make_booking(
            self.customer, self.profile, package, make_location_type(),
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00', status_name='in_progress',
        )

    def request(self, booking=None, client=None):
        return (client or self.artist_client).put(
            REQUEST, {'booking_id': (booking or self.booking).booking_id}, format='json')

    def fresh(self):
        self.booking.refresh_from_db()
        return self.booking

    def sent(self):
        return Notification.objects.filter(booking_id=self.booking.booking_id, type='completion_pin_ready',
                                           user_id=self.customer.user_id)

    def test_request_issues_the_pin_notifies_the_customer_and_completes_the_flow(self):
        self.assertIsNone(self.fresh().completion_pin)
        resp = self.request()
        self.assertEqual(resp.status_code, 200, resp.content)
        booking = self.fresh()
        self.assertEqual(len(str(booking.completion_pin)), 4)
        self.assertGreater(booking.completion_pin_expiry, timezone.now())
        self.assertEqual(self.sent().count(), 1)
        self.assertNotIn('completion_pin', str(resp.json()).lower().replace('completion pin sent', ''))   # never returned to the artist
        got = self.customer_client.get(CUSTOMER_GET, {'booking_id': booking.booking_id})
        self.assertEqual(got.status_code, 200)
        done = self.artist_client.put(VERIFY, {'booking_id': booking.booking_id,
                                               'completion_pin': got.data['data']['completionPin']}, format='json')
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.fresh().status.name, 'completed')

    def test_verifying_before_requesting_is_a_clear_error_and_not_a_failed_attempt(self):
        resp = self.artist_client.put(VERIFY, {'booking_id': self.booking.booking_id, 'completion_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Request the Completion PIN first', resp.json()['message'])
        self.assertEqual(self.fresh().completion_pin_attempts, 0)

    def test_customer_cannot_read_a_pin_that_was_not_requested(self):
        self.assertEqual(self.customer_client.get(CUSTOMER_GET, {'booking_id': self.booking.booking_id}).status_code, 400)

    def test_only_an_in_progress_booking(self):
        for status_name in ('confirmed', 'pending', 'completed', 'cancelled'):
            Booking.objects.filter(booking_id=self.booking.booking_id).update(
                status_id=__import__('sunndari_apps.core.models.booking_status', fromlist=['BookingStatus']).BookingStatus.objects.get(name=status_name).status_id)
            self.assertEqual(self.request().status_code, 400, status_name)
        self.assertIsNone(self.fresh().completion_pin)
        self.assertFalse(self.sent().exists())

    def test_another_artist_or_a_customer_cannot_request_it(self):
        other_client, _, _ = make_artist(phone_number='+919000007003')
        self.assertEqual(self.request(client=other_client).status_code, 400)
        self.assertEqual(self.request(client=self.customer_client).status_code, 400)
        self.assertIsNone(self.fresh().completion_pin)

    def test_requires_authentication(self):
        from rest_framework.test import APIClient
        self.assertEqual(self.request(client=APIClient()).status_code, 401)

    def test_asking_again_within_a_minute_is_refused_and_sends_nothing_more(self):
        self.request()
        pin = self.fresh().completion_pin
        again = self.request()
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.sent().count(), 1)
        self.assertEqual(self.fresh().completion_pin, pin)

    def test_asking_again_later_resends_the_same_pin_and_keeps_the_attempt_counter(self):
        self.request()
        pin = self.fresh().completion_pin
        Booking.objects.filter(booking_id=self.booking.booking_id).update(completion_pin_attempts=3)
        self.sent().update(created_at=timezone.now() - timedelta(minutes=2))
        self.assertEqual(self.request().status_code, 200)
        booking = self.fresh()
        self.assertEqual(booking.completion_pin, pin)                   # same PIN, not re-rolled
        self.assertEqual(booking.completion_pin_attempts, 3)            # no fresh set of guesses
        self.assertEqual(self.sent().count(), 2)

    def test_an_expired_pin_is_replaced(self):
        self.request()
        Booking.objects.filter(booking_id=self.booking.booking_id).update(
            completion_pin_expiry=timezone.now() - timedelta(minutes=5), completion_pin_attempts=4)
        self.sent().update(created_at=timezone.now() - timedelta(minutes=2))
        self.assertEqual(self.request().status_code, 200)
        booking = self.fresh()
        self.assertGreater(booking.completion_pin_expiry, timezone.now())
        self.assertEqual(booking.completion_pin_attempts, 0)

    def test_a_service_that_overran_its_slot_still_gets_a_usable_pin(self):
        Booking.objects.filter(booking_id=self.booking.booking_id).update(booking_date=timezone.now().date() - timedelta(days=3))
        self.assertEqual(self.request().status_code, 200)
        self.assertGreater(self.fresh().completion_pin_expiry, timezone.now() + timedelta(hours=1))

    def test_a_booking_that_already_has_a_pin_from_before_this_change_keeps_working(self):
        Booking.objects.filter(booking_id=self.booking.booking_id).update(
            completion_pin=4321, completion_pin_expiry=timezone.now() + timedelta(hours=3))
        resp = self.artist_client.put(VERIFY, {'booking_id': self.booking.booking_id, 'completion_pin': 4321}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_request_validation(self):
        for body in ({}, {'booking_id': None}, {'booking_id': 'abc'}, {'booking_id': -1}, {'booking_id': 10 ** 12}, {'booking_id': 1.5}):
            resp = self.artist_client.put(REQUEST, body, format='json')
            self.assertEqual(resp.status_code, 400, body)
        self.assertEqual(self.artist_client.put(REQUEST, format='json').status_code, 400)       # no body at all
        self.assertIsNone(self.fresh().completion_pin)
        self.assertFalse(self.sent().exists())

    def test_wrong_http_method_is_refused(self):
        for method in ('get', 'post', 'delete'):
            resp = getattr(self.artist_client, method)(REQUEST, {'booking_id': self.booking.booking_id})
            self.assertEqual(resp.status_code, 405, method)

