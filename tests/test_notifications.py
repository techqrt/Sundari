from datetime import datetime, timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.notifications.models import Notification
from sunndari_apps.notifications.utils import NotificationGateway, NotificationService
from sunndari_apps.notifications.tasks import send_appointment_reminders
from sunndari_apps.customers.models import Booking

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_location_type,
    make_package, make_booking, seed_booking_statuses, seed_payment_statuses, next_weekday,
)


# ─── Notification Endpoints ───────────────────────────────────────────────────

class NotificationEndpointTest(TestCase):
    get_url = '/notifications/get/'
    get_all_url = '/notifications/get_all/'
    mark_read_url = '/notifications/mark_read/'
    mark_all_read_url = '/notifications/mark_all_read/'

    def test_get_notification_returns_200(self):
        client, user = make_customer(phone_number='+919000000400')
        notification_id = Notification().create(user_id=user.user_id, title='Hi', message='Hello there')
        resp = client.get(self.get_url, {'notification_id': notification_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['notificationId'], notification_id)
        self.assertFalse(resp.data['data']['isRead'])

    def test_get_another_users_notification_returns_400(self):
        client, _ = make_customer(phone_number='+919000000401')
        _, other_user = make_customer(phone_number='+919000000402')
        notification_id = Notification().create(user_id=other_user.user_id, title='Hi', message='Hello')
        resp = client.get(self.get_url, {'notification_id': notification_id})
        self.assertEqual(resp.status_code, 400)

    def test_get_all_notifications_returns_own_only(self):
        client, user = make_customer(phone_number='+919000000403')
        Notification().create(user_id=user.user_id, title='A', message='msg a')
        _, other_user = make_customer(phone_number='+919000000404')
        Notification().create(user_id=other_user.user_id, title='B', message='msg b')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_mark_read_returns_200(self):
        client, user = make_customer(phone_number='+919000000405')
        notification_id = Notification().create(user_id=user.user_id, title='Hi', message='Hello')
        resp = client.put(self.mark_read_url, {'notification_id': notification_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Notification.objects.get(notification_id=notification_id).is_read)

    def test_mark_all_read_returns_200(self):
        client, user = make_customer(phone_number='+919000000406')
        Notification().create(user_id=user.user_id, title='A', message='msg a')
        Notification().create(user_id=user.user_id, title='B', message='msg b')
        resp = client.put(self.mark_all_read_url, {}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Notification.objects.filter(user_id=user.user_id, is_read=False).count(), 0)

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 401)


# ─── Gateway Stub ──────────────────────────────────────────────────────────────

class NotificationGatewayStubTest(TestCase):

    def test_send_returns_unconfigured_stub(self):
        result = NotificationGateway.send(user_id=1, title='t', message='m')
        self.assertFalse(result['success'])

    def test_notify_creates_row_with_failed_delivery(self):
        client, user = make_customer(phone_number='+919000000410')
        notification_id = NotificationService.notify(
            user_id=user.user_id, title='Test', message='msg', type='generic',
        )
        notification = Notification.objects.get(notification_id=notification_id)
        self.assertEqual(notification.delivery_status, 'failed')
        self.assertIsNotNone(notification.failure_reason)


# ─── Event Hooks ───────────────────────────────────────────────────────────────

class NotificationEventHookTest(TestCase):

    def test_create_booking_notifies_artist(self):
        seed_booking_statuses()
        customer_client, _ = make_customer(phone_number='+919000000420')
        _, artist_user, profile = make_artist(phone_number='+919000000421')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        from sunndari_apps.artists.models import ArtistLocationPreference, ArtistAvailabilitySchedule
        ArtistLocationPreference.add(artist_id=profile.artist_id, location_type_id=location_type.location_type_id)
        booking_date = next_weekday(2)
        ArtistAvailabilitySchedule.objects.create(
            artist=profile, day_of_week=booking_date.weekday(), start_time='09:00:00', end_time='18:00:00',
        )
        resp = customer_client.post('/customers/bookings/create/', {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            Notification.objects.filter(user_id=artist_user.user_id, type='new_booking_alert').exists()
        )

    def test_confirm_booking_notifies_customer(self):
        artist_client, _, profile = make_artist(phone_number='+919000000422')
        _, customer = make_customer(phone_number='+919000000423')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        resp = artist_client.put('/artists/bookings/update_status/', {
            'booking_id': booking.booking_id, 'status': 'confirmed',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(user_id=customer.user_id, type='booking_confirmed').exists()
        )

    def test_payment_webhook_notifies_customer(self):
        seed_payment_statuses()
        customer_client, customer = make_customer(phone_number='+919000000424')
        _, _, profile = make_artist(phone_number='+919000000425')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        init_resp = customer_client.post('/customers/payments/initiate/', {'booking_id': booking.booking_id}, format='json')
        gateway_order_id = init_resp.data['data']['gateway_order_id']

        webhook_client = APIClient()
        webhook_resp = webhook_client.post('/customers/payments/webhook/', {
            'gateway_order_id': gateway_order_id,
            'gateway_payment_id': 'txn_1',
            'status': 'paid',
        }, format='json')
        self.assertEqual(webhook_resp.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(user_id=customer.user_id, type='payment_status').exists()
        )


# ─── Appointment Reminder Task ─────────────────────────────────────────────────

class AppointmentReminderTaskTest(TestCase):

    def _confirmed_booking_at(self, hours_from_now: float, customer_phone, artist_phone):
        _, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        target_dt = timezone.now() + timedelta(hours=hours_from_now)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=target_dt.date(), start_time=target_dt.time().replace(microsecond=0),
            end_time=(target_dt + timedelta(hours=1)).time().replace(microsecond=0),
            status_name='confirmed',
        )
        return customer, booking

    def test_sends_24h_reminder(self):
        customer, booking = self._confirmed_booking_at(24.0, '+919000000430', '+919000000431')
        sent = send_appointment_reminders()
        self.assertEqual(sent['booking_reminder_24h'], 1)
        self.assertTrue(
            Notification.objects.filter(user_id=customer.user_id, type='booking_reminder_24h', booking_id=booking.booking_id).exists()
        )

    def test_sends_2h_reminder(self):
        customer, booking = self._confirmed_booking_at(2.0, '+919000000432', '+919000000433')
        sent = send_appointment_reminders()
        self.assertEqual(sent['booking_reminder_2h'], 1)

    def test_does_not_duplicate_reminder_on_second_run(self):
        self._confirmed_booking_at(24.0, '+919000000434', '+919000000435')
        first = send_appointment_reminders()
        second = send_appointment_reminders()
        self.assertEqual(first['booking_reminder_24h'], 1)
        self.assertEqual(second['booking_reminder_24h'], 0)

    def test_no_reminder_outside_window(self):
        self._confirmed_booking_at(12.0, '+919000000436', '+919000000437')
        sent = send_appointment_reminders()
        self.assertEqual(sent['booking_reminder_24h'], 0)
        self.assertEqual(sent['booking_reminder_2h'], 0)
