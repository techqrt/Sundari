from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.artists.models import ArtistAvailabilityBlock
from sunndari_apps.customers.models import Booking, BookingReschedule
from sunndari_apps.customers.models.booking import IST
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import (
    make_customer, make_artist, make_package, make_location_type, make_schedule,
    seed_booking_statuses, make_booking, next_weekday,
)


class RescheduleBase(TestCase):
    request_url = '/artists/bookings/reschedule/request/'
    cancel_url = '/artists/bookings/reschedule/cancel/'
    respond_url = '/customers/bookings/reschedule/respond/'

    def setUp(self):
        seed_booking_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000003000')
        self.customer_client, self.customer = make_customer(phone_number='+919000003001')
        self.package = make_package(self.profile, price=2000, duration=90)
        self.location = make_location_type('Home Visit')
        self.original_date = next_weekday(2)
        self.new_date = self.original_date + timedelta(days=1)
        for date in (self.original_date, self.new_date):
            make_schedule(self.profile, day_of_week=date.weekday(), start='09:00:00', end='18:00:00')
        self.booking = self._booking(self.original_date, '10:00', '11:30')

    def _booking(self, date, start, end, status='confirmed', customer=None):
        booking = make_booking(customer or self.customer, self.profile, self.package, self.location, date, start, end,
                               status_name=status)
        Booking.generate_booking_otp(booking.booking_id, date, booking.end_time)
        return Booking.objects.get(booking_id=booking.booking_id)

    def _request(self, date=None, start='14:00:00', booking=None, client=None, **extra):
        return (client or self.artist_client).post(self.request_url, {
            'booking_id': (booking or self.booking).booking_id,
            'proposed_date': (date or self.new_date).strftime('%d-%m-%y'),
            'proposed_start_time': start, **extra,
        }, format='json')

    def _respond(self, reschedule_id, decision, client=None):
        return (client or self.customer_client).put(self.respond_url, {
            'reschedule_id': reschedule_id, 'decision': decision}, format='json')

    def _pending(self, **kwargs):
        resp = self._request(**kwargs)
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data['data']['reschedule_id']


class RescheduleRequestTest(RescheduleBase):
    def test_request_creates_pending_record_and_leaves_booking_untouched(self):
        resp = self._request(reason='Stuck in traffic')
        self.assertEqual(resp.status_code, 201)
        reschedule = BookingReschedule.objects.get(reschedule_id=resp.data['data']['reschedule_id'])
        self.assertEqual(reschedule.status, 'pending')
        self.assertEqual((reschedule.previous_date, str(reschedule.previous_start_time)), (self.original_date, '10:00:00'))
        self.assertEqual((reschedule.proposed_date, str(reschedule.proposed_start_time)), (self.new_date, '14:00:00'))
        self.assertEqual(str(reschedule.proposed_end_time), '15:30:00')      # 90-minute appointment keeps its length
        self.assertEqual(reschedule.requested_by_id, self.artist_user.user_id)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.booking_date, str(self.booking.start_time)), (self.original_date, '10:00:00'))
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='reschedule_requested').exists())
        expected_expiry = min(timezone.now() + timedelta(hours=24), Booking.to_aware(self.original_date, time(10, 0)))
        self.assertLess(abs((reschedule.expires_at - expected_expiry).total_seconds()), 60)

    def test_both_sides_can_list_and_filter_by_booking(self):
        reschedule_id = self._pending()
        other = self._booking(self.original_date, '15:00', '16:30')
        for client in (self.artist_client, self.customer_client):
            base = '/artists' if client is self.artist_client else '/customers'
            rows = client.get(f'{base}/bookings/reschedule/get_all/').data['data']['data']
            self.assertEqual([row['rescheduleId'] for row in rows], [reschedule_id])
            self.assertEqual((rows[0]['status'], rows[0]['proposedStartTime']), ('pending', '14:00:00'))
            filtered = client.get(f'{base}/bookings/reschedule/get_all/', {
                'filter_key': 'bookingId', 'filter_value': other.booking_id}).data['data']['data']
            self.assertEqual(filtered, [])

    def test_only_confirmed_unstarted_bookings(self):
        pending_booking = self._booking(self.original_date, '12:00', '13:30', status='pending')
        self.assertEqual(self._request(booking=pending_booking).status_code, 400)
        Booking.objects.filter(booking_id=self.booking.booking_id).update(on_my_way_at=timezone.now())
        self.assertEqual(self._request().status_code, 400)
        self.assertEqual(BookingReschedule.objects.count(), 0)

    def test_cancelled_completed_and_started_slots_are_refused(self):
        for status in ('cancelled', 'completed', 'in_progress', 'no_show'):
            booking = self._booking(self.original_date, '12:00', '13:30', status=status)
            self.assertEqual(self._request(booking=booking).status_code, 400, status)

    def test_booking_already_past_its_start_cannot_be_rescheduled(self):
        past_booking = make_booking(self.customer, self.profile, self.package, self.location,
                                    timezone.now().astimezone(IST).date() - timedelta(days=1), '10:00', '11:30',
                                    status_name='confirmed')
        self.assertEqual(self._request(booking=past_booking).status_code, 400)

    def test_only_the_bookings_artist_can_request(self):
        other_client, _, _ = make_artist(phone_number='+919000003002')
        self.assertEqual(self._request(client=other_client).status_code, 400)
        self.assertEqual(self._request(client=self.customer_client).status_code, 400)
        self.assertEqual(self._request(client=APIClient()).status_code, 401)
        self.assertEqual(BookingReschedule.objects.count(), 0)

    def test_one_open_request_per_booking_in_api_and_database(self):
        self._pending()
        self.assertEqual(self._request(start='15:00:00').status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookingReschedule.objects.create(
                booking_id=self.booking.booking_id, requested_by_id=self.artist_user.user_id,
                previous_date=self.original_date, previous_start_time=time(10), previous_end_time=time(11, 30),
                proposed_date=self.new_date, proposed_start_time=time(16), proposed_end_time=time(17, 30),
                expires_at=timezone.now() + timedelta(hours=1),
            )

    def test_proposal_validation(self):
        self.assertEqual(self._request(date=self.original_date, start='10:00:00').status_code, 400)          # same slot
        self.assertEqual(self._request(date=timezone.now().astimezone(IST).date() - timedelta(days=1)).status_code, 400)
        now_ist = timezone.now().astimezone(IST)
        soon = now_ist + timedelta(minutes=30)
        self.assertEqual(self._request(date=soon.date(), start=soon.strftime('%H:%M:%S')).status_code, 400)  # < 2h ahead
        self.assertEqual(self._request(start='08:00:00').status_code, 400)                                    # before working hours
        self.assertEqual(self._request(start='17:00:00').status_code, 400)                                    # ends after 18:00
        self.assertEqual(self._request(start='23:30:00').status_code, 400)                                    # crosses midnight
        ArtistAvailabilityBlock.objects.create(artist=self.profile, block_date=self.new_date)
        self.assertEqual(self._request().status_code, 400)                                                    # blocked day
        self.assertEqual(self._request(date=self.new_date + timedelta(days=2)).status_code, 400)             # no schedule that day
        self.assertEqual(BookingReschedule.objects.count(), 0)

    def test_conflicts_with_other_active_bookings_but_not_with_itself(self):
        self._booking(self.new_date, '14:00', '15:30')
        self.assertEqual(self._request(start='14:30:00').status_code, 400)
        self.assertEqual(self._request(date=self.original_date, start='10:30:00').status_code, 201)           # overlaps only itself

    def test_cancelled_bookings_do_not_block_the_proposed_slot(self):
        self._booking(self.new_date, '14:00', '15:30', status='cancelled')
        self.assertEqual(self._request().status_code, 201)

    def test_request_validation_errors(self):
        for payload in ({'proposed_date': 'tomorrow'}, {'proposed_start_time': 'noon'}, {'booking_id': 'x'}):
            body = {'booking_id': self.booking.booking_id, 'proposed_date': self.new_date.strftime('%d-%m-%y'),
                    'proposed_start_time': '14:00:00', **payload}
            self.assertEqual(self.artist_client.post(self.request_url, body, format='json').status_code, 400)

    def test_artist_can_withdraw_only_own_pending_request(self):
        reschedule_id = self._pending()
        other_client, _, _ = make_artist(phone_number='+919000003003')
        self.assertEqual(other_client.put(self.cancel_url, {'reschedule_id': reschedule_id}, format='json').status_code, 400)
        self.assertEqual(self.artist_client.put(self.cancel_url, {'reschedule_id': reschedule_id}, format='json').status_code, 200)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'cancelled')
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='reschedule_cancelled').exists())
        self.assertEqual(self.artist_client.put(self.cancel_url, {'reschedule_id': reschedule_id}, format='json').status_code, 400)
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.assertEqual(self._request().status_code, 201)                                                    # can ask again


class RescheduleResponseTest(RescheduleBase):
    def test_accept_moves_the_booking_and_refreshes_otp_expiry_without_changing_the_otp(self):
        otp_before = self.booking.booking_otp
        reschedule_id = self._pending()
        resp = self._respond(reschedule_id, 'accepted')
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.booking_date, str(self.booking.start_time), str(self.booking.end_time)),
                         (self.new_date, '14:00:00', '15:30:00'))
        self.assertEqual(self.booking.booking_otp, otp_before)
        self.assertEqual(self.booking.booking_otp_expiry, Booking.to_aware(self.new_date, time(15, 30)) + timedelta(hours=2))
        reschedule = BookingReschedule.objects.get(reschedule_id=reschedule_id)
        self.assertEqual(reschedule.status, 'accepted')
        self.assertIsNotNone(reschedule.responded_at)
        self.assertEqual((reschedule.previous_date, str(reschedule.previous_start_time)), (self.original_date, '10:00:00'))
        self.assertTrue(Notification.objects.filter(user_id=self.artist_user.user_id, type='reschedule_accepted').exists())
        shown = self.customer_client.get('/customers/bookings/get/', {'booking_id': self.booking.booking_id}).data['data']
        self.assertEqual((shown['bookingDate'], shown['startTime']), (self.new_date.isoformat(), '14:00:00'))
        self.assertEqual(shown['statusId'], self.booking.status_id)

    def test_reject_leaves_everything_unchanged(self):
        reschedule_id = self._pending()
        self.assertEqual(self._respond(reschedule_id, 'rejected').status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.booking_date, str(self.booking.start_time)), (self.original_date, '10:00:00'))
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'rejected')
        self.assertTrue(Notification.objects.filter(user_id=self.artist_user.user_id, type='reschedule_rejected').exists())
        self.assertEqual(self._request().status_code, 201)

    def test_a_request_can_only_be_answered_once(self):
        reschedule_id = self._pending()
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 200)
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.assertEqual(self._respond(reschedule_id, 'rejected').status_code, 400)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'accepted')
        self.assertEqual(Notification.objects.filter(type='reschedule_accepted').count(), 1)

    def test_only_the_bookings_customer_can_respond(self):
        reschedule_id = self._pending()
        other_customer, _ = make_customer(phone_number='+919000003004')
        self.assertEqual(self._respond(reschedule_id, 'accepted', client=other_customer).status_code, 400)
        self.assertEqual(self._respond(reschedule_id, 'accepted', client=self.artist_client).status_code, 400)
        self.assertEqual(self._respond(reschedule_id, 'accepted', client=APIClient()).status_code, 401)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'pending')
        self.assertEqual(self._respond(reschedule_id, 'maybe').status_code, 400)
        self.assertEqual(self._respond(999999, 'accepted').status_code, 400)

    def test_accept_fails_cleanly_if_the_slot_was_taken_meanwhile(self):
        reschedule_id = self._pending()
        self._booking(self.new_date, '14:30', '16:00', customer=make_customer(phone_number='+919000003005')[1])
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.booking_date, str(self.booking.start_time)), (self.original_date, '10:00:00'))
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'pending')
        self.assertEqual(self._respond(reschedule_id, 'rejected').status_code, 200)

    def test_accept_fails_if_the_day_was_blocked_meanwhile(self):
        reschedule_id = self._pending()
        ArtistAvailabilityBlock.objects.create(artist=self.profile, block_date=self.new_date)
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_date, self.original_date)

    def test_accept_fails_if_the_artist_already_set_off(self):
        reschedule_id = self._pending()
        Booking.objects.filter(booking_id=self.booking.booking_id).update(on_my_way_at=timezone.now())
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_date, self.original_date)

    def test_unanswered_request_expires_and_can_no_longer_be_accepted(self):
        reschedule_id = self._pending()
        BookingReschedule.objects.filter(reschedule_id=reschedule_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'expired')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_date, self.original_date)
        self.assertEqual(self._request().status_code, 201)                      # an expired request doesn't block a new one

    def test_listing_marks_stale_requests_expired(self):
        reschedule_id = self._pending()
        BookingReschedule.objects.filter(reschedule_id=reschedule_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        rows = self.customer_client.get('/customers/bookings/reschedule/get_all/').data['data']['data']
        self.assertEqual(rows[0]['status'], 'expired')

    def test_cancelling_the_booking_closes_the_open_request(self):
        reschedule_id = self._pending()
        self.assertEqual(self.customer_client.put('/customers/bookings/cancel/', {
            'booking_id': self.booking.booking_id}, format='json').status_code, 200)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'cancelled')
        self.assertEqual(self._respond(reschedule_id, 'accepted').status_code, 400)

    def test_artist_cancelling_the_booking_closes_the_open_request(self):
        reschedule_id = self._pending()
        resp = self.artist_client.put('/artists/bookings/update_status/', {
            'booking_id': self.booking.booking_id, 'status': 'cancelled', 'reason': 'ill'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'cancelled')

    def test_missed_booking_closes_the_open_request(self):
        reschedule_id = self._pending()
        from sunndari_apps.core.models import BookingStatus
        Booking.mark_missed(self.booking.booking_id, BookingStatus.objects.get(name='no_show').status_id)
        self.assertEqual(BookingReschedule.objects.get(reschedule_id=reschedule_id).status, 'cancelled')

    def test_artist_cannot_see_other_artists_requests_and_customer_only_their_own(self):
        self._pending()
        other_client, _, _ = make_artist(phone_number='+919000003006')
        self.assertEqual(other_client.get('/artists/bookings/reschedule/get_all/').data['data']['data'], [])
        other_customer, _ = make_customer(phone_number='+919000003007')
        self.assertEqual(other_customer.get('/customers/bookings/reschedule/get_all/').data['data']['data'], [])
        self.assertEqual(APIClient().get('/customers/bookings/reschedule/get_all/').status_code, 401)

    def test_after_acceptance_the_lifecycle_continues_on_the_new_slot(self):
        """The rescheduled booking must still be a normal booking: another request is possible
        and its old slot is free for someone else."""
        self._respond(self._pending(), 'accepted')
        replacement = self._booking(self.original_date, '10:00', '11:30', customer=make_customer(phone_number='+919000003008')[1])
        self.assertEqual(replacement.status.name, 'confirmed')
        self.assertEqual(self._request(date=self.new_date, start='16:00:00').status_code, 201)
