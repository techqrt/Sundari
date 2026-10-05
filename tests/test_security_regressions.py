"""Permanent regression tests for the defects found by the full-flow QA run (docs/qa/).
Each class names the finding id (Q-nn) it guards."""
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.users.utils import UsersUtils

from tests.test_authentication import make_user, make_authenticated_client


class Q01_ProfileTokenLeakTest(TestCase):
    url = '/users/profile/get/'

    def setUp(self):
        self.victim_client, self.victim = make_authenticated_client(phone_number='+919800100001', email='victim@example.com', fcm_token='victim-device-token')
        self.attacker_client, self.attacker = make_authenticated_client(phone_number='+919800100002')
        self.admin_client, self.admin = make_authenticated_client(phone_number='+919800100003', role='admin')

    def _no_credentials(self, resp):
        text = resp.content.decode()
        secrets = (self.victim.access_token, self.victim.refresh_token, self.admin.access_token, self.attacker.access_token, 'access_token', 'accessToken')
        for secret in filter(None, secrets):          # (some fixtures have no refresh token: '' is "in" everything)
            self.assertNotIn(secret, text)

    def test_another_user_sees_only_a_label_never_credentials_or_contact_details(self):
        resp = self.attacker_client.get(self.url, {'user_id': self.victim.user_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data['data']), {'userId', 'name', 'role'})
        self._no_credentials(resp)
        for private in ('victim@example.com', '+919800100001', 'victim-device-token'):
            self.assertNotIn(private, resp.content.decode())

    def test_admin_token_cannot_be_read_by_a_customer(self):
        resp = self.attacker_client.get(self.url, {'user_id': self.admin.user_id})
        self._no_credentials(resp)
        # the old attack: use the leaked admin token on an admin route
        self.assertNotEqual(self.admin_client.get('/admin-panel/artists/review_queue/get_all/').status_code, 401)
        self.assertEqual(self.attacker_client.get('/admin-panel/artists/review_queue/get_all/').status_code, 400)

    def test_owner_sees_own_profile_without_the_bearer_token(self):
        resp = self.victim_client.get(self.url, {'user_id': self.victim.user_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertEqual((data['email'], data['phoneNumber'], data['fcmToken']), ('victim@example.com', '+919800100001', 'victim-device-token'))
        self._no_credentials(resp)

    def test_admin_sees_contact_details_but_still_no_credentials_or_device_token(self):
        resp = self.admin_client.get(self.url, {'user_id': self.victim.user_id})
        data = resp.data['data']
        self.assertEqual(data['email'], 'victim@example.com')
        self.assertNotIn('fcmToken', data)
        self._no_credentials(resp)

    def test_other_users_private_columns_cannot_be_requested_via_values(self):
        resp = self.attacker_client.get(self.url, {'user_id': self.victim.user_id, 'values': 'userId,email'})
        self.assertEqual(resp.status_code, 400)
        resp = self.attacker_client.get(self.url, {'user_id': self.victim.user_id, 'values': 'access_token'})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_user_and_unauthenticated(self):
        self.assertEqual(self.attacker_client.get(self.url, {'user_id': 999999}).status_code, 400)
        self.assertEqual(APIClient().get(self.url, {'user_id': self.victim.user_id}).status_code, 401)

    def test_mapper_only_emits_mapped_columns(self):
        out = UsersUtils(entity='profile').mapper([{'user_id': 1, 'name': 'x', 'access_token': 'SECRET', 'refresh_token': 'SECRET2', 'otp': 123456}])
        self.assertIn('"userId"', out)
        for leaked in ('SECRET', 'access_token', 'refresh_token', 'otp', '123456'):
            self.assertNotIn(leaked, out)

    def test_revoke_all_sessions_command(self):
        call_command('revoke_all_sessions', stdout=io.StringIO(), stderr=io.StringIO())     # no --yes: refuses
        self.assertEqual(self.victim_client.get(self.url, {'user_id': self.victim.user_id}).status_code, 200)
        call_command('revoke_all_sessions', '--yes', stdout=io.StringIO())
        self.assertEqual(self.victim_client.get(self.url, {'user_id': self.victim.user_id}).status_code, 401)
        self.assertEqual(User.objects.exclude(access_token='').count(), 0)


# ═════════════════════════════════════════════════════════════════════════════
# Findings Q-02 … Q-15
# ═════════════════════════════════════════════════════════════════════════════
import os
import contextlib
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import DatabaseError
from django.test import override_settings

from sunndari_apps.artists.models import ArtistProfile, ArtistDocument, Portfolio
from sunndari_apps.core.models import BookingStatus, ApprovalStatus
from sunndari_apps.customers.models import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.models import Payment

from tests.test_artists import make_image_bytes, make_sub_category, make_category, make_authenticated_client as make_artist_client
from tests.test_customers import (
    make_customer, make_artist, make_package, make_location_type, make_location_preference, make_schedule,
    seed_booking_statuses, seed_payment_statuses, next_weekday, make_booking, make_paid_payment,
)


def _bookable(phone):
    seed_booking_statuses()
    client, user, profile = make_artist(phone_number=phone)
    package = make_package(profile, price=1500)
    location = make_location_type('Studio')
    make_location_preference(profile, location)
    date = next_weekday(2)
    make_schedule(profile, day_of_week=date.weekday())
    return client, user, profile, package, location, date


def _book(customer_client, profile, package, location, date, start='10:00:00'):
    return customer_client.post('/customers/bookings/create/', {
        'artist_id': profile.artist_id, 'package_id': package.package_id, 'location_type_id': location.location_type_id,
        'booking_date': date.strftime('%d-%m-%y'), 'start_time': start}, format='json')


class Q02_SelfBookingTest(TestCase):
    def test_artist_cannot_book_own_services(self):
        client, user, profile, package, location, date = _bookable('+919800200001')
        resp = _book(client, profile, package, location, date)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_other_customers_and_other_artists_can_still_book(self):
        _, _, profile, package, location, date = _bookable('+919800200002')
        customer, _ = make_customer(phone_number='+919800200003')
        self.assertEqual(_book(customer, profile, package, location, date).status_code, 201)
        other_artist, _, _ = make_artist(phone_number='+919800200004')
        self.assertEqual(_book(other_artist, profile, package, location, date, start='13:00:00').status_code, 201)


class Q03_CustomerCancelCutoffTest(TestCase):
    def setUp(self):
        seed_booking_statuses(); seed_payment_statuses()
        self.customer_client, self.customer = make_customer(phone_number='+919800200010')
        _, _, self.profile = make_artist(phone_number='+919800200011')
        self.package = make_package(self.profile)
        self.location = make_location_type('Studio')

    def _booking(self, status, **fields):
        b = make_booking(self.customer, self.profile, self.package, self.location, next_weekday(3), '10:00', '11:00', status_name=status)
        if fields:
            Booking.objects.filter(booking_id=b.booking_id).update(**fields)
        make_paid_payment(b)
        return b.booking_id

    def _cancel(self, bid):
        return self.customer_client.put('/customers/bookings/cancel/', {'booking_id': bid}, format='json')

    def test_in_progress_cannot_be_cancelled_or_refunded(self):
        bid = self._booking('in_progress')
        self.assertEqual(self._cancel(bid).status_code, 400)
        self.assertEqual(Booking.objects.get(booking_id=bid).status.name, 'in_progress')
        self.assertEqual(Payment.objects.get(booking_id=bid).status.name, 'paid')

    def test_cannot_cancel_after_the_artist_has_arrived(self):
        from django.utils import timezone
        bid = self._booking('confirmed', arrived_at=timezone.now())
        self.assertEqual(self._cancel(bid).status_code, 400)
        self.assertEqual(Booking.objects.get(booking_id=bid).status.name, 'confirmed')

    def test_pending_and_confirmed_before_arrival_can_still_be_cancelled(self):
        for status in ('pending', 'confirmed'):
            bid = self._booking(status)
            Booking.objects.filter(booking_id=bid).update(start_time='12:00', end_time='13:00')
            self.assertEqual(self._cancel(bid).status_code, 200, status)
            self.assertEqual(Booking.objects.get(booking_id=bid).status.name, 'cancelled')


class Q07_NonObjectBodyTest(TestCase):
    def test_non_object_json_bodies_get_a_controlled_400_everywhere(self):
        client, _ = make_authenticated_client(phone_number='+919800200020')
        cases = [('put', '/users/profile/update/'), ('post', '/users/address/create/'), ('post', '/chat/messages/create/'),
                 ('post', '/customers/bookings/create/'), ('post', '/help_center/messages/create/'), ('put', '/notifications/mark_read/')]
        for method, url in cases:
            for raw in ([], ['x'], 'text', 123):
                resp = getattr(client, method)(url, raw, format='json')
                self.assertEqual(resp.status_code, 400, (url, raw))
                self.assertFalse(resp.json()['status'])

    def test_null_body_on_an_endpoint_with_required_fields_is_a_400(self):
        client, _ = make_authenticated_client(phone_number='+919800200022')
        self.assertEqual(client.post('/chat/messages/create/', None, format='json').status_code, 400)

    def test_valid_objects_are_unaffected(self):
        client, user = make_authenticated_client(phone_number='+919800200021')
        self.assertEqual(client.put('/users/profile/update/', {'name': 'Fine'}, format='json').status_code, 200)
        self.assertEqual(client.put('/users/profile/update/', {'name': 'Form'}, format='multipart').status_code, 200)


class Q08_NotificationFailureNeverFailsTheBusinessActionTest(TestCase):
    def setUp(self):
        self.client_a, self.user_a, self.profile, self.package, self.location, self.date = _bookable('+919800200030')
        self.customer_client, self.customer = make_customer(phone_number='+919800200031')

    def test_booking_succeeds_when_notifications_cannot_be_written(self):
        with patch('sunndari_apps.notifications.utils.Notification.create', side_effect=DatabaseError('notification table locked')):
            resp = _book(self.customer_client, self.profile, self.package, self.location, self.date)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Booking.objects.count(), 1)

    def test_booking_succeeds_when_the_otp_sms_provider_is_down(self):
        with patch('sunndari_apps.customers.views.create_booking.send_otp_sms', side_effect=RuntimeError('sms down')):
            resp = _book(self.customer_client, self.profile, self.package, self.location, self.date)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Booking.objects.count(), 1)

    def test_retry_after_a_flaky_notification_does_not_report_a_false_failure(self):
        with patch('sunndari_apps.notifications.utils.NotificationService._notify', side_effect=RuntimeError('boom')):
            first = _book(self.customer_client, self.profile, self.package, self.location, self.date)
        self.assertEqual(first.status_code, 201)

    def test_artist_status_change_is_not_rolled_back_by_a_notification_failure(self):
        b = make_booking(self.customer, self.profile, self.package, self.location, self.date, '14:00', '15:00')
        make_paid_payment(b)
        with patch('sunndari_apps.notifications.utils.NotificationService._notify', side_effect=RuntimeError('boom')):
            resp = self.client_a.put('/artists/bookings/update_status/', {'booking_id': b.booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Booking.objects.get(booking_id=b.booking_id).status.name, 'confirmed')

    def test_a_database_error_inside_notify_does_not_poison_the_outer_transaction(self):
        from django.db import transaction
        from sunndari_apps.notifications.utils import NotificationService
        with transaction.atomic():
            Booking.objects.count()
            with patch('sunndari_apps.notifications.utils.Notification.create', side_effect=DatabaseError('x')):
                self.assertIsNone(NotificationService.notify(user_id=self.customer.user_id, title='t', message='m'))
            self.assertEqual(Booking.objects.count(), 0)          # the outer transaction is still usable


class Q09_OtpNotLoggedOutsideDebugTest(TestCase):
    def test_otp_is_not_printed_when_debug_is_off(self):
        from sunndari_apps.authentication.utils import send_otp_sms
        buffer = io.StringIO()
        with override_settings(DEBUG=False), contextlib.redirect_stdout(buffer), self.assertLogs('sunndari_apps.authentication.utils', level='INFO') as logs:
            send_otp_sms('+919812345678', 482913)
        self.assertNotIn('482913', buffer.getvalue())
        self.assertNotIn('482913', '\n'.join(logs.output))
        self.assertNotIn('+919812345678', '\n'.join(logs.output))          # masked

    def test_developers_still_see_it_in_debug(self):
        from sunndari_apps.authentication.utils import send_otp_sms
        buffer = io.StringIO()
        with override_settings(DEBUG=True), contextlib.redirect_stdout(buffer):
            send_otp_sms('+919812345678', 482913)
        self.assertIn('482913', buffer.getvalue())


class Q10_InactiveAccountsGetNoTokenTest(TestCase):
    def setUp(self):
        self.user = make_user(phone_number='+919800200040', email='inactive@example.com')
        self.user.set_password('Zr7!kQp2mWx')
        self.user.is_active = False
        self.user.save()

    def test_password_login(self):
        resp = APIClient().post('/auth/login/', {'username': '+919800200040', 'password': 'Zr7!kQp2mWx'})
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn('access_token', resp.content.decode())
        self.user.refresh_from_db()
        self.assertEqual(self.user.access_token, '')

    def test_otp_login(self):
        self.user.generate_otp()
        resp = APIClient().post('/auth/phone-otp/verify/', {'phone_number': '+919800200040', 'otp': str(self.user.otp)})
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn('access_token', resp.content.decode())

    def test_token_refresh(self):
        from sunndari_apps.authentication.utils import generate_refresh_token
        self.user.refresh_token = generate_refresh_token(self.user)
        self.user.save()
        resp = APIClient().post('/auth/token/refresh/', {'refresh_token': self.user.refresh_token})
        self.assertEqual(resp.status_code, 403)

    def test_active_users_are_unaffected(self):
        self.user.is_active = True
        self.user.save()
        self.assertEqual(APIClient().post('/auth/login/', {'username': '+919800200040', 'password': 'Zr7!kQp2mWx'}).status_code, 200)


class Q11_WeakPasswordsTest(TestCase):
    def _register(self, password, phone):
        return APIClient().post('/auth/register/', {'name': 'N', 'phone_number': phone, 'password': password, 'role': 'customer'}, format='json')

    def test_weak_passwords_rejected_strong_accepted(self):
        for i, weak in enumerate(('12345678', '00000000', 'password', 'qwertyuiop', '11111111', 'iloveyou')):
            self.assertEqual(self._register(weak, f'+91980020005{i}').status_code, 400, weak)
        self.assertEqual(self._register('Zr7!kQp2mWx', '+919800200059').status_code, 200)

    def test_reset_password_applies_the_same_rule(self):
        user = make_user(phone_number='+919800200060')
        user.generate_otp()
        resp = APIClient().post('/auth/reset-password/', {'username': '+919800200060', 'otp': str(user.otp), 'new_password': '12345678'})
        self.assertEqual(resp.status_code, 400)
        user.refresh_from_db()
        self.assertIsNotNone(user.otp)             # the code was not consumed by a rejected password


class Q12_BankAccountNumberIsDigitsTest(TestCase):
    def test_letters_and_symbols_rejected(self):
        client, _ = make_artist_client(phone_number='+919800200070')
        base = {'account_holder_name': 'A', 'ifsc_code': 'HDFC0001234'}
        for bad in ('ABCDEFGHIJ12', '1234-5678-90', '12345 67890', '123456789O12', '１２３４５６７８'):
            resp = client.put('/artists/payout_account/set/', {**base, 'bank_account_number': bad}, format='json')
            self.assertEqual(resp.status_code, 400, bad)

    def test_digits_accepted(self):
        client, _ = make_artist_client(phone_number='+919800200071')
        resp = client.put('/artists/payout_account/set/', {'account_holder_name': 'A', 'ifsc_code': 'HDFC0001234', 'bank_account_number': '123456789012'}, format='json')
        self.assertEqual(resp.status_code, 200)


class Q13_RepeatApprovalIsAPureNoOpTest(TestCase):
    def test_second_approval_adds_no_feedback_and_no_notification(self):
        from tests.test_admin_panel import make_admin_client, verify_id_proof
        from tests.test_artists import make_authenticated_client as make_artist_client, get_artist_profile, complete_onboarding_steps
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        artist_client, artist_user = make_artist_client(phone_number='+919800200080')
        complete_onboarding_steps(artist_client, artist_user)
        artist_client.post('/artists/onboarding/submit/', {}, format='json')
        profile = get_artist_profile(artist_user)
        admin_client, _ = make_admin_client(phone_number='+919400200081')
        verify_id_proof(admin_client, profile)
        for _ in range(3):
            self.assertEqual(admin_client.put('/admin-panel/artists/approve/', {'artist_id': profile.artist_id}, format='json').status_code, 200)
        history = artist_client.get('/artists/review/feedback/get_all/').data['data']['data']
        self.assertEqual([h['decision'] for h in history], ['approved'])
        self.assertEqual(Notification.objects.filter(user_id=artist_user.user_id, type='artist_approved').count(), 1)


class Q14_Q15_NoOrphanedFilesTest(TestCase):
    def test_portfolio_delete_removes_the_media_file(self):
        client, user = make_artist_client(phone_number='+919800200090')
        sub = make_sub_category(category=make_category(name='OrphanCat'), name='OrphanSub')
        pid = client.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': sub.sub_category_id,
                          'file': SimpleUploadedFile('p.png', make_image_bytes('PNG'), content_type='image/png')}, format='multipart').data['data']['portfolio_id']
        path = os.path.join(settings.MEDIA_ROOT, Portfolio.objects.get(portfolio_id=pid).file.name)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(client.delete(f'/artists/portfolio/delete/?portfolio_id={pid}').status_code, 200)
        self.assertFalse(os.path.exists(path))

    def test_failed_kyc_upload_leaves_no_row_and_no_file(self):
        client, user = make_artist_client(phone_number='+919800200091')
        count_files = lambda: sum(len(f) for _, _, f in os.walk(settings.PRIVATE_MEDIA_ROOT))
        before_files, before_rows = count_files(), ArtistDocument.objects.count()
        with patch('sunndari_apps.artists.models.document.ArtistDocument.replace_id_proofs', side_effect=RuntimeError('db')):
            resp = client.post('/artists/documents/create/', {
                'document_type': 'id_proof', 'id_type': 'aadhaar', 'document_number': '234567890123',
                'file': SimpleUploadedFile('f.png', make_image_bytes('PNG'), content_type='image/png'),
                'back_file': SimpleUploadedFile('b.png', make_image_bytes('PNG'), content_type='image/png')}, format='multipart')
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertEqual(ArtistDocument.objects.count(), before_rows)
        self.assertEqual(count_files(), before_files)


# ═════════════════════════════════════════════════════════════════════════════
# Q-04 overpayment · Q-05 real refunds · Q-06 slot lock
# ═════════════════════════════════════════════════════════════════════════════
import datetime
from unittest.mock import MagicMock

import razorpay
from django.utils import timezone

from sunndari_apps.core.models import PaymentStatus
from sunndari_apps.payments.models import PaymentOrder


class _Gateway:
    """Razorpay stand-in: emulates order create/fetch and payment fetch/refund like the app calls them."""
    current_order = None

    def __init__(self, refund_error=None):
        self.orders = {}
        self.client = MagicMock()

        def create(data):
            order = {'id': f"order_{data['receipt']}", 'amount': data['amount'], 'currency': 'INR', 'status': 'created'}
            self.orders[order['id']] = order
            return order
        self.client.order.create.side_effect = create
        self.client.order.fetch.side_effect = lambda oid: {**self.orders[oid], 'amount_paid': self.orders[oid]['amount'], 'status': 'paid'}
        self.client.payment.fetch.side_effect = lambda pid: {'id': pid, 'status': 'captured', 'order_id': _Gateway.current_order}
        if refund_error:
            self.client.payment.refund.side_effect = refund_error

    def __enter__(self):
        self.patches = [patch(target, return_value=self.client) for target in (
            'sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client',
            'sunndari_apps.payments.views.verify_payment.RazorpayGateway.get_client',
            'sunndari_apps.payments.models.RazorpayGateway.get_client')]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


class _MoneyBase(TestCase):
    def setUp(self):
        seed_booking_statuses(); seed_payment_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919800300001')
        self.package = make_package(self.profile, price=2000)
        self.location = make_location_type('Studio')
        make_location_preference(self.profile, self.location)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        self.customer_client, self.customer = make_customer(phone_number='+919800300002')
        self.booking_id = _book(self.customer_client, self.profile, self.package, self.location, self.date).data['data']['booking_id']

    def _initiate(self, **kw):
        return self.customer_client.post('/customers/payments/initiate/', {'booking_id': self.booking_id, **kw}, format='json')

    def _verify(self, order_id):
        _Gateway.current_order = order_id
        return self.customer_client.post('/customers/payments/verify/', {'razorpay_order_id': order_id, 'razorpay_payment_id': 'pay_x', 'razorpay_signature': 's'}, format='json')

    def _settled(self):
        return Payment.total_settled_for_booking(booking_id=self.booking_id)


class Q04_NoOverpaymentTest(_MoneyBase):
    def test_double_tap_returns_the_same_order(self):
        with _Gateway():
            first = self._initiate()
            second = self._initiate()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['data']['gateway_order_id'], second.data['data']['gateway_order_id'])
        self.assertEqual(first.data['data']['payment_id'], second.data['data']['payment_id'])
        self.assertEqual(Payment.objects.filter(booking_id=self.booking_id).count(), 1)

    def test_cannot_start_orders_that_together_exceed_the_remaining_due(self):
        with _Gateway():
            self.assertEqual(self._initiate(amount='500.00', payment_type='advance').status_code, 201)
            self.assertEqual(self._initiate().status_code, 400)                          # 500 pending + 2000 > 2000
            self.assertEqual(self._initiate(amount='1500.00', payment_type='balance').status_code, 201)   # exactly fits
            self.assertEqual(self._initiate(amount='100.00', payment_type='balance').status_code, 400)
        self.assertEqual(Payment.objects.filter(booking_id=self.booking_id).count(), 2)

    def test_an_abandoned_order_stops_blocking_after_the_window(self):
        with _Gateway():
            self._initiate(amount='500.00', payment_type='advance')
            Payment.objects.filter(booking_id=self.booking_id).update(created_at=timezone.now() - datetime.timedelta(hours=2))
            self.assertEqual(self._initiate().status_code, 201)

    def test_verification_refuses_a_capture_that_would_overpay(self):
        """Even if two orders somehow exist (created directly, bypassing /initiate/), the second
        capture is not applied: the booking can never be settled for more than its total."""
        pending = PaymentStatus.objects.get(name='pending')
        for n in (1, 2):
            Payment().create(booking_id=self.booking_id, customer_id=self.customer.user_id, artist_id=self.profile.artist_id,
                             amount=Decimal('2000.00'), commission_amount=Decimal('200'), artist_payout_amount=Decimal('1800'), status_id=pending.status_id)
            Payment.objects.filter(payment_id=Payment.objects.latest('payment_id').payment_id).update(gateway_order_id=f'order_dup_{n}')
        with _Gateway() as gw:
            gw.orders.update({f'order_dup_{n}': {'id': f'order_dup_{n}', 'amount': 200000} for n in (1, 2)})
            first, second = self._verify('order_dup_1'), self._verify('order_dup_2')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(self._settled(), Decimal('2000.00'))
        failed = Payment.objects.get(gateway_order_id='order_dup_2')
        self.assertEqual(failed.status.name, 'failed')
        self.assertIn('Overpayment', failed.failure_reason)

    def test_group_order_that_would_overpay_is_refused_atomically(self):
        pending, paid = PaymentStatus.objects.get(name='pending'), PaymentStatus.objects.get(name='paid')
        Payment().create(booking_id=self.booking_id, customer_id=self.customer.user_id, artist_id=self.profile.artist_id, amount=Decimal('2000.00'),
                         commission_amount=Decimal('200'), artist_payout_amount=Decimal('1800'), status_id=paid.status_id)
        order = PaymentOrder()
        order_id = order.create(customer_id=self.customer.user_id, total_amount=Decimal('2000.00'), status_id=pending.status_id)
        Payment().create(booking_id=self.booking_id, customer_id=self.customer.user_id, artist_id=self.profile.artist_id, amount=Decimal('2000.00'),
                         commission_amount=Decimal('200'), artist_payout_amount=Decimal('1800'), status_id=pending.status_id, order_id=order_id)
        self.assertFalse(PaymentOrder.mark_paid_checked(order_id=order_id, gateway_payment_id='pay_g', status_id=paid.status_id))
        self.assertEqual(PaymentOrder.objects.get(order_id=order_id).status.name, 'pending')
        self.assertEqual(self._settled(), Decimal('2000.00'))

    def test_normal_advance_then_balance_flow_still_settles_exactly(self):
        with _Gateway():
            first = self._initiate(amount='500.00', payment_type='advance')
            self.assertEqual(self._verify(first.data['data']['gateway_order_id']).status_code, 200)
            second = self._initiate()
            self.assertEqual(second.status_code, 201)
            self.assertEqual(Payment.objects.get(payment_id=second.data['data']['payment_id']).amount, Decimal('1500.00'))
            self.assertEqual(self._verify(second.data['data']['gateway_order_id']).status_code, 200)
        self.assertEqual(self._settled(), Decimal('2000.00'))


class Q05_RealRefundsTest(_MoneyBase):
    def _paid_payment(self, **extra):
        paid = PaymentStatus.objects.get(name='paid')
        pid = Payment().create(booking_id=self.booking_id, customer_id=self.customer.user_id, artist_id=self.profile.artist_id, amount=Decimal('2000.00'),
                               commission_amount=Decimal('200'), artist_payout_amount=Decimal('1800'), status_id=paid.status_id)
        Payment.objects.filter(payment_id=pid).update(gateway='razorpay', gateway_payment_id='pay_real_1', **extra)
        return pid

    def _confirm(self):
        self.artist_client.put('/artists/bookings/update_status/', {'booking_id': self.booking_id, 'status': 'confirmed'}, format='json')

    def test_customer_cancel_requests_the_refund_from_the_gateway(self):
        pid = self._paid_payment(); self._confirm()
        with _Gateway() as gw:
            resp = self.customer_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        gw.client.payment.refund.assert_called_once_with('pay_real_1', {'amount': 200000, 'notes': {'payment_id': str(pid), 'booking_id': str(self.booking_id)}})
        self.assertEqual(Payment.objects.get(payment_id=pid).status.name, 'refunded')
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='refund_initiated').exists())

    def test_artist_cancel_also_refunds_through_the_gateway(self):
        pid = self._paid_payment(); self._confirm()
        with _Gateway() as gw:
            resp = self.artist_client.put('/artists/bookings/update_status/', {'booking_id': self.booking_id, 'status': 'cancelled', 'reason': 'ill'}, format='json')
        self.assertEqual(resp.status_code, 200)
        gw.client.payment.refund.assert_called_once()
        self.assertEqual(Payment.objects.get(payment_id=pid).status.name, 'refunded')

    def test_a_gateway_failure_never_claims_the_money_was_returned(self):
        pid = self._paid_payment(); self._confirm()
        with _Gateway(refund_error=razorpay.errors.BadRequestError('gateway down')):
            resp = self.customer_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(resp.status_code, 200)                                           # the booking is still cancelled
        self.assertEqual(Booking.objects.get(booking_id=self.booking_id).status.name, 'cancelled')
        payment = Payment.objects.get(payment_id=pid)
        self.assertEqual(payment.status.name, 'paid')
        self.assertTrue(payment.failure_reason.startswith('Refund failed'))
        self.assertTrue(Notification.objects.filter(user_id=self.customer.user_id, type='refund_pending').exists())
        self.assertFalse(Notification.objects.filter(user_id=self.customer.user_id, type='refund_initiated').exists())

    def test_retry_command_completes_a_failed_refund(self):
        pid = self._paid_payment(); self._confirm()
        with _Gateway(refund_error=razorpay.errors.BadRequestError('down')):
            self.customer_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        with _Gateway() as gw:
            call_command('retry_refunds', stdout=io.StringIO())
        gw.client.payment.refund.assert_called_once()
        payment = Payment.objects.get(payment_id=pid)
        self.assertEqual((payment.status.name, payment.failure_reason), ('refunded', None))
        with _Gateway() as gw:                                                             # nothing left to retry
            call_command('retry_refunds', stdout=io.StringIO())
        gw.client.payment.refund.assert_not_called()

    def test_wallet_only_payments_need_no_gateway_call(self):
        pid = self._paid_payment()
        Payment.objects.filter(payment_id=pid).update(gateway='wallet', gateway_payment_id=None, amount=Decimal('0.00'))
        self._confirm()
        with _Gateway() as gw:
            self.customer_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        gw.client.payment.refund.assert_not_called()
        self.assertEqual(Payment.objects.get(payment_id=pid).status.name, 'refunded')

    def test_only_cash_is_refunded_by_the_gateway(self):
        """A payment that used coins only has the gateway's cash part refunded (the coins are returned by the wallet)."""
        pid = self._paid_payment()
        Payment.objects.filter(payment_id=pid).update(amount=Decimal('1500.00'))
        self._confirm()
        with _Gateway() as gw:
            self.customer_client.put('/customers/bookings/cancel/', {'booking_id': self.booking_id}, format='json')
        self.assertEqual(gw.client.payment.refund.call_args[0][1]['amount'], 150000)


class Q06_ArtistRowIsLockedForBookingsTest(TestCase):
    def test_slot_check_locks_the_artist_profile_row(self):
        from django.db.models.query import QuerySet
        _, _, profile, package, location, date = _bookable('+919800300010')
        customer, _ = make_customer(phone_number='+919800300011')
        locked_models = []
        original = QuerySet.select_for_update

        def spy(self, *args, **kwargs):
            locked_models.append(self.model.__name__)
            return original(self, *args, **kwargs)
        with patch.object(QuerySet, 'select_for_update', spy):
            resp = _book(customer, profile, package, location, date)
        self.assertEqual(resp.status_code, 201)
        self.assertIn('ArtistProfile', locked_models)
        self.assertLess(locked_models.index('ArtistProfile'), locked_models.index('Booking'))      # artist first, then bookings
