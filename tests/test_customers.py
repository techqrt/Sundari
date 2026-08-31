from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.artists.models import (
    ArtistProfile, PricingPackage, ArtistLocationPreference, ArtistAvailabilitySchedule,
)
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType, ApprovalStatus, BookingStatus, PaymentStatus,
)
from sunndari_apps.users.models.customer_address import CustomerAddress
from sunndari_apps.customers.models import Booking, Payment, Review
from sunndari_apps.notifications.models.notification import Notification


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_user(phone_number, role, name='Test User'):
    return User.objects.create(phone_number=phone_number, role=role, name=name)


def make_client(user):
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_customer(phone_number='+919000000100', name='Test Customer'):
    user = make_user(phone_number, 'customer', name)
    return make_client(user), user


def make_artist(phone_number='+919000000200', name='Test Artist', approved=True):
    ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
    user = make_user(phone_number, 'artist', name)
    ArtistProfile.create_for_user(user_id=user.user_id)
    profile = ArtistProfile.objects.get(user_id=user.user_id)
    if approved:
        approved_status, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        profile.approval_status = approved_status
        profile.save()
    return make_client(user), user, profile


def make_category(name='Bridal Makeup'):
    category, _ = ServiceCategory.objects.get_or_create(name=name)
    return category


def make_sub_category(category=None, name='Full Bridal Makeup'):
    if category is None:
        category = make_category()
    sub_category, _ = ServiceSubCategory.objects.get_or_create(category=category, name=name)
    return sub_category


def make_location_type(name='Home Visit'):
    location_type, _ = LocationType.objects.get_or_create(name=name)
    return location_type


def make_package(profile, sub_category=None, price=1500, duration=60, is_active=True, name='Basic Package'):
    if sub_category is None:
        sub_category = make_sub_category()
    pkg = PricingPackage()
    package_id = pkg.create(
        artist_id=profile.artist_id, sub_category_id=sub_category.sub_category_id,
        name=name, price=price, duration_minutes=duration,
    )
    saved = PricingPackage.objects.get(package_id=package_id)
    if not is_active:
        saved.is_active = False
        saved.save()
    return saved


def make_location_preference(profile, location_type):
    ArtistLocationPreference.add(artist_id=profile.artist_id, location_type_id=location_type.location_type_id)


def make_schedule(profile, day_of_week, start='09:00:00', end='18:00:00'):
    return ArtistAvailabilitySchedule.objects.create(
        artist=profile, day_of_week=day_of_week, start_time=start, end_time=end,
    )


def seed_booking_statuses():
    for name in ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show']:
        BookingStatus.objects.get_or_create(name=name, defaults={'description': name})


def seed_payment_statuses():
    for name in ['pending', 'paid', 'failed', 'refunded', 'partially_refunded']:
        PaymentStatus.objects.get_or_create(name=name, defaults={'description': name})


def make_booking(customer, profile, package, location_type, booking_date, start_time, end_time, status_name='pending', address=None):
    seed_booking_statuses()
    status = BookingStatus.objects.get(name=status_name)
    booking = Booking()
    booking_id = booking.create(
        customer_id=customer.user_id, artist_id=profile.artist_id, sub_category_id=package.sub_category_id,
        package_id=package.package_id, location_type_id=location_type.location_type_id,
        booking_date=booking_date, start_time=start_time, end_time=end_time,
        status_id=status.status_id, total_amount=package.price,
        address_id=address.address_id if address else None,
    )
    return Booking.objects.get(booking_id=booking_id)


def next_weekday(target_weekday: int) -> date:
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    days_ahead = days_ahead if days_ahead else 7
    return today + timedelta(days=days_ahead)


# ─── Search & Discovery ───────────────────────────────────────────────────────

class SearchArtistTest(TestCase):
    url = '/customers/artists/search/'

    def test_search_returns_approved_artist_with_active_package(self):
        client, _ = make_customer()
        _, _, profile = make_artist()
        make_package(profile)
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_search_excludes_unapproved_artist(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000201', approved=False)
        make_package(profile)
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 0)

    def test_search_excludes_artist_without_active_package(self):
        client, _ = make_customer()
        make_artist(phone_number='+919000000202')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 0)

    def test_search_filters_by_city(self):
        client, _ = make_customer()
        _, _, profile1 = make_artist(phone_number='+919000000203')
        profile1.city = 'Faridabad'
        profile1.save()
        make_package(profile1)
        _, _, profile2 = make_artist(phone_number='+919000000204')
        profile2.city = 'Mumbai'
        profile2.save()
        make_package(profile2)
        resp = client.get(self.url, {'city': 'Faridabad'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)
        self.assertEqual(resp.data['data']['data'][0]['city'], 'Faridabad')

    def test_search_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Artist Profile View (Customer Side) ──────────────────────────────────────

class ArtistDetailTest(TestCase):
    url = '/customers/artists/get/'

    def test_get_detail_returns_profile_and_packages(self):
        client, _ = make_customer()
        _, _, profile = make_artist()
        make_package(profile)
        resp = client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['profile']['artistId'], profile.artist_id)
        self.assertEqual(len(resp.data['data']['packages']), 1)

    def test_get_detail_excludes_inactive_package(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000210')
        make_package(profile, is_active=False)
        resp = client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['packages']), 0)

    def test_get_detail_unapproved_artist_returns_400(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000211', approved=False)
        resp = client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 400)


# ─── Availability Check ───────────────────────────────────────────────────────

class CheckAvailabilityTest(TestCase):
    url = '/customers/artists/availability/'

    def test_availability_returns_working_window(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000220')
        booking_date = next_weekday(2)
        make_schedule(profile, day_of_week=booking_date.weekday())
        resp = client.get(self.url, {
            'artist_id': profile.artist_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data['data']['workingWindow'])
        self.assertFalse(resp.data['data']['isBlocked'])


# ─── Create Booking ───────────────────────────────────────────────────────────

class CreateBookingTest(TestCase):
    url = '/customers/bookings/create/'

    def _setup_bookable_artist(self, phone_number='+919000000230', booking_weekday=2):
        _, _, profile = make_artist(phone_number=phone_number)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=1500, duration=60)
        location_type = make_location_type()
        make_location_preference(profile, location_type)
        booking_date = next_weekday(booking_weekday)
        make_schedule(profile, day_of_week=booking_date.weekday())
        seed_booking_statuses()
        return profile, package, location_type, booking_date

    def test_create_booking_success(self):
        client, _ = make_customer()
        profile, package, location_type, booking_date = self._setup_bookable_artist()
        resp = client.post(self.url, {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('booking_id', resp.data['data'])
        booking = Booking.objects.get(booking_id=resp.data['data']['booking_id'])
        self.assertEqual(str(booking.total_amount), '1500.00')
        self.assertIsNotNone(booking.expires_at)

    def test_create_booking_generates_and_delivers_booking_otp(self):
        client, _ = make_customer()
        profile, package, location_type, booking_date = self._setup_bookable_artist(phone_number='+919000000233')
        resp = client.post(self.url, {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        booking = Booking.objects.get(booking_id=resp.data['data']['booking_id'])

        self.assertIsNotNone(booking.booking_otp)
        self.assertEqual(len(str(booking.booking_otp)), 6)
        self.assertIsNotNone(booking.booking_otp_expiry)
        self.assertGreater(booking.booking_otp_expiry, booking.created_at)
        self.assertEqual(booking.booking_otp_attempts, 0)
        self.assertIsNone(booking.booking_otp_verified_at)

        otp_notification = Notification.objects.filter(
            booking_id=booking.booking_id, type='booking_otp_issued', user_id=profile.user_id,
        ).first()
        self.assertIsNotNone(otp_notification)
        self.assertIn(str(booking.booking_otp), otp_notification.message)

    def test_create_booking_outside_schedule_returns_400(self):
        client, _ = make_customer()
        profile, package, location_type, booking_date = self._setup_bookable_artist(phone_number='+919000000231')
        resp = client.post(self.url, {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '23:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_create_booking_location_not_offered_returns_400(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000232')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        other_location = make_location_type(name='Salon / Studio')
        booking_date = next_weekday(2)
        make_schedule(profile, day_of_week=booking_date.weekday())
        seed_booking_statuses()
        resp = client.post(self.url, {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': other_location.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_create_booking_double_booking_returns_400(self):
        client, _ = make_customer(phone_number='+919000000240')
        client2, _ = make_customer(phone_number='+919000000241')
        profile, package, location_type, booking_date = self._setup_bookable_artist(phone_number='+919000000233')
        payload = {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': booking_date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }
        resp1 = client.post(self.url, payload, format='json')
        self.assertEqual(resp1.status_code, 201)
        resp2 = client2.post(self.url, payload, format='json')
        self.assertEqual(resp2.status_code, 400)

    def test_create_booking_unapproved_artist_returns_400(self):
        client, _ = make_customer()
        _, _, profile = make_artist(phone_number='+919000000234', approved=False)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        seed_booking_statuses()
        resp = client.post(self.url, {
            'artist_id': profile.artist_id,
            'package_id': package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': next_weekday(2).strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── Customer Booking Get / Get All / Cancel ─────────────────────────────────

class CustomerBookingTest(TestCase):
    get_url = '/customers/bookings/get/'
    get_all_url = '/customers/bookings/get_all/'
    cancel_url = '/customers/bookings/cancel/'

    def _make_booking(self, customer, artist_phone='+919000000250', status_name='pending'):
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        return make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name=status_name,
        )

    def test_get_booking_returns_200(self):
        client, customer = make_customer()
        booking = self._make_booking(customer)
        resp = client.get(self.get_url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['bookingId'], booking.booking_id)

    def test_get_another_customers_booking_returns_400(self):
        client, _ = make_customer(phone_number='+919000000251')
        _, other_customer = make_customer(phone_number='+919000000252')
        booking = self._make_booking(other_customer, artist_phone='+919000000253')
        resp = client.get(self.get_url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_get_all_bookings_returns_own_only(self):
        client, customer = make_customer(phone_number='+919000000254')
        self._make_booking(customer, artist_phone='+919000000255')
        _, other_customer = make_customer(phone_number='+919000000256')
        self._make_booking(other_customer, artist_phone='+919000000257')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_cancel_pending_booking_returns_200(self):
        client, customer = make_customer(phone_number='+919000000258')
        booking = self._make_booking(customer, artist_phone='+919000000259')
        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id, 'reason': 'Change of plans'}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertEqual(booking.cancelled_by, 'customer')

    def test_cancel_booking_invalidates_booking_otp(self):
        client, customer = make_customer(phone_number='+919000000260')
        booking = self._make_booking(customer, artist_phone='+919000000261')
        booking.booking_otp = 654321
        booking.booking_otp_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id, 'reason': 'Change of plans'}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertEqual(booking.cancelled_by, 'customer')
        self.assertIsNone(booking.booking_otp)
        self.assertIsNone(booking.booking_otp_expiry)

    def test_cancel_completed_booking_returns_400(self):
        client, customer = make_customer(phone_number='+919000000260')
        booking = self._make_booking(customer, artist_phone='+919000000261', status_name='completed')
        resp = client.put(self.cancel_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 401)


# ─── Artist Booking Get / Get All / Update Status ─────────────────────────────

class ArtistBookingTest(TestCase):
    get_all_url = '/artists/bookings/get_all/'
    update_status_url = '/artists/bookings/update_status/'

    def _make_booking(self, profile, customer_phone='+919000000270', status_name='pending'):
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        _, customer = make_customer(phone_number=customer_phone)
        return make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name=status_name,
        )

    def test_artist_get_all_bookings(self):
        client, _, profile = make_artist(phone_number='+919000000271')
        self._make_booking(profile, customer_phone='+919000000272')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_confirm_pending_booking_returns_200(self):
        client, _, profile = make_artist(phone_number='+919000000273')
        booking = self._make_booking(profile, customer_phone='+919000000274')
        resp = client.put(self.update_status_url, {'booking_id': booking.booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'confirmed')

    def test_reject_pending_booking_invalidates_booking_otp(self):
        client, _, profile = make_artist(phone_number='+919000000280')
        booking = self._make_booking(profile, customer_phone='+919000000281')
        booking.booking_otp = 123456
        booking.booking_otp_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        resp = client.put(self.update_status_url, {'booking_id': booking.booking_id, 'status': 'cancelled'}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'cancelled')
        self.assertEqual(booking.cancelled_by, 'artist')
        self.assertIsNone(booking.booking_otp)
        self.assertIsNone(booking.booking_otp_expiry)

    def test_invalid_transition_returns_400(self):
        client, _, profile = make_artist(phone_number='+919000000275')
        booking = self._make_booking(profile, customer_phone='+919000000276', status_name='completed')
        resp = client.put(self.update_status_url, {'booking_id': booking.booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_update_status_on_another_artists_booking_returns_400(self):
        client, _, _ = make_artist(phone_number='+919000000277')
        _, _, other_profile = make_artist(phone_number='+919000000278')
        booking = self._make_booking(other_profile, customer_phone='+919000000279')
        resp = client.put(self.update_status_url, {'booking_id': booking.booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── Artist On My Way ──────────────────────────────────────────────────────────

class OnMyWayTest(TestCase):
    url = '/artists/bookings/on_my_way/'

    def _make_confirmed_booking(self, profile, customer_phone, booking_date, start_time='10:00:00', end_time='11:00:00'):
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        _, customer = make_customer(phone_number=customer_phone)
        return make_booking(
            customer, profile, package, location_type,
            booking_date=booking_date, start_time=start_time, end_time=end_time,
            status_name='confirmed',
        )

    def test_on_my_way_within_2h_window_returns_200(self):
        client, _, profile = make_artist(phone_number='+919000000290')
        now = timezone.now()
        booking_dt = now + timedelta(hours=1)
        booking = self._make_confirmed_booking(
            profile, '+919000000291', booking_dt.date(),
            start_time=booking_dt.time().strftime('%H:%M:%S'),
            end_time=(booking_dt + timedelta(hours=1)).time().strftime('%H:%M:%S'),
        )
        resp = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.on_my_way_at)

    def test_on_my_way_more_than_2h_before_returns_400(self):
        client, _, profile = make_artist(phone_number='+919000000292')
        now = timezone.now()
        booking_dt = now + timedelta(hours=5)
        booking = self._make_confirmed_booking(
            profile, '+919000000293', booking_dt.date(),
            start_time=booking_dt.time().strftime('%H:%M:%S'),
            end_time=(booking_dt + timedelta(hours=1)).time().strftime('%H:%M:%S'),
        )
        resp = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNone(booking.on_my_way_at)

    def test_on_my_way_already_marked_returns_400(self):
        client, _, profile = make_artist(phone_number='+919000000294')
        now = timezone.now()
        booking_dt = now + timedelta(hours=1)
        booking = self._make_confirmed_booking(
            profile, '+919000000295', booking_dt.date(),
            start_time=booking_dt.time().strftime('%H:%M:%S'),
            end_time=(booking_dt + timedelta(hours=1)).time().strftime('%H:%M:%S'),
        )
        first = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(first.status_code, 200)
        second = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_on_my_way_on_pending_booking_returns_400(self):
        client, _, profile = make_artist(phone_number='+919000000296')
        booking = self._make_confirmed_booking(profile, '+919000000297', next_weekday(2))
        booking.status = BookingStatus.objects.get(name='pending')
        booking.save()
        resp = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_on_my_way_on_another_artists_booking_returns_400(self):
        client, _, _ = make_artist(phone_number='+919000000298')
        _, _, other_profile = make_artist(phone_number='+919000000299')
        now = timezone.now()
        booking_dt = now + timedelta(hours=1)
        booking = self._make_confirmed_booking(
            other_profile, '+919000000209', booking_dt.date(),
            start_time=booking_dt.time().strftime('%H:%M:%S'),
            end_time=(booking_dt + timedelta(hours=1)).time().strftime('%H:%M:%S'),
        )
        resp = client.put(self.url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 400)


# ─── Artist Arrived (Booking OTP verification) ─────────────────────────────────

class ArrivedTest(TestCase):
    url = '/artists/bookings/arrived/'

    def _make_on_my_way_booking(self, artist_phone, customer_phone, otp=111111):
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        customer_client, customer = make_customer(phone_number=customer_phone)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        booking.on_my_way_at = timezone.now()
        booking.booking_otp = otp
        booking.booking_otp_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        return artist_client, customer_client, booking

    def test_arrived_with_correct_otp_returns_200_and_generates_start_pin(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000300', '+919000000301')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.arrived_at)
        self.assertIsNotNone(booking.booking_otp_verified_at)
        self.assertIsNone(booking.booking_otp)
        self.assertIsNone(booking.booking_otp_expiry)
        self.assertIsNotNone(booking.start_service_pin)
        self.assertEqual(len(str(booking.start_service_pin)), 4)

    def test_arrived_with_incorrect_otp_returns_400_and_does_not_arrive(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000302', '+919000000303')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 999999}, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNone(booking.arrived_at)
        self.assertIsNone(booking.start_service_pin)
        self.assertEqual(booking.booking_otp_attempts, 1)

    def test_arrived_with_expired_otp_returns_400(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000304', '+919000000305')
        booking.booking_otp_expiry = timezone.now() - timedelta(minutes=1)
        booking.save()
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNone(booking.arrived_at)

    def test_arrived_locks_out_after_5_failed_attempts(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000306', '+919000000307')
        for _ in range(5):
            resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 999999}, format='json')
            self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.booking_otp_locked_until)
        locked_resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(locked_resp.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNone(booking.arrived_at)

    def test_arrived_before_on_my_way_returns_400(self):
        artist_client, artist_user, profile = make_artist(phone_number='+919000000308')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        _, customer = make_customer(phone_number='+919000000309')
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        booking.booking_otp = 111111
        booking.booking_otp_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_arrived_twice_returns_400(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000310', '+919000000311')
        first = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(first.status_code, 200)
        booking.refresh_from_db()
        second = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_arrived_on_another_artists_booking_returns_400(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000312', '+919000000313')
        other_client, _, _ = make_artist(phone_number='+919000000314')
        resp = other_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_arrived_notifies_customer_and_creates_start_pin_notification(self):
        artist_client, _, booking = self._make_on_my_way_booking('+919000000315', '+919000000316')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'booking_otp': 111111}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Notification.objects.filter(booking_id=booking.booking_id, type='artist_arrived').exists())
        self.assertTrue(Notification.objects.filter(booking_id=booking.booking_id, type='start_pin_ready').exists())


# ─── Customer Get Start PIN ─────────────────────────────────────────────────────

class GetStartPinTest(TestCase):
    url = '/customers/bookings/start_pin/'

    def _arrived_booking(self, artist_phone, customer_phone):
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        customer_client, customer = make_customer(phone_number=customer_phone)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        booking.on_my_way_at = timezone.now()
        booking.booking_otp = 222222
        booking.booking_otp_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        artist_client.put(
            '/artists/bookings/arrived/', {'booking_id': booking.booking_id, 'booking_otp': 222222}, format='json',
        )
        booking.refresh_from_db()
        return customer_client, booking

    def test_get_start_pin_after_arrival_returns_200(self):
        customer_client, booking = self._arrived_booking('+919000000320', '+919000000321')
        resp = customer_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['startServicePin'], booking.start_service_pin)

    def test_get_start_pin_before_arrival_returns_400(self):
        customer_client, customer = make_customer(phone_number='+919000000322')
        _, _, profile = make_artist(phone_number='+919000000323')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        resp = customer_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_get_start_pin_for_another_customers_booking_returns_400(self):
        _, booking = self._arrived_booking('+919000000324', '+919000000325')
        outsider_client, _ = make_customer(phone_number='+919000000326')
        resp = outsider_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)


# ─── Artist Verify Start PIN ────────────────────────────────────────────────────

class VerifyStartPinTest(TestCase):
    url = '/artists/bookings/start_pin/verify/'

    def _make_arrived_booking(self, artist_phone, customer_phone, pin=1234):
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        customer_client, customer = make_customer(phone_number=customer_phone)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        booking.on_my_way_at = timezone.now()
        booking.arrived_at = timezone.now()
        booking.start_service_pin = pin
        booking.start_pin_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        return artist_client, customer_client, booking

    def test_verify_correct_pin_starts_service_and_generates_completion_pin(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000330', '+919000000331')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')
        self.assertIsNotNone(booking.service_started_at)
        self.assertIsNone(booking.start_service_pin)
        self.assertIsNone(booking.start_pin_expiry)
        self.assertIsNotNone(booking.completion_pin)
        self.assertEqual(len(str(booking.completion_pin)), 4)

    def test_verify_incorrect_pin_returns_400_and_does_not_start(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000332', '+919000000333')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 9999}, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'confirmed')
        self.assertIsNone(booking.service_started_at)
        self.assertEqual(booking.start_pin_attempts, 1)

    def test_verify_expired_pin_returns_400(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000334', '+919000000335')
        booking.start_pin_expiry = timezone.now() - timedelta(minutes=1)
        booking.save()
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_locks_out_after_5_failed_attempts(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000336', '+919000000337')
        for _ in range(5):
            resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 9999}, format='json')
            self.assertEqual(resp.status_code, 400)
        locked_resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(locked_resp.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'confirmed')

    def test_verify_pin_before_arrival_returns_400(self):
        artist_client, artist_user, profile = make_artist(phone_number='+919000000338')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        _, customer = make_customer(phone_number='+919000000339')
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_twice_returns_400(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000340', '+919000000341')
        first = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(first.status_code, 200)
        second = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_verify_pin_on_another_artists_booking_returns_400(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000342', '+919000000343')
        other_client, _, _ = make_artist(phone_number='+919000000344')
        resp = other_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_notifies_customer(self):
        artist_client, _, booking = self._make_arrived_booking('+919000000345', '+919000000346')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'start_service_pin': 1234}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Notification.objects.filter(booking_id=booking.booking_id, type='service_started').exists())
        self.assertTrue(Notification.objects.filter(booking_id=booking.booking_id, type='completion_pin_ready').exists())


# ─── Customer Get Completion PIN ────────────────────────────────────────────────

class GetCompletionPinTest(TestCase):
    url = '/customers/bookings/completion_pin/'

    def _in_progress_booking(self, artist_phone, customer_phone):
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        customer_client, customer = make_customer(phone_number=customer_phone)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        booking.on_my_way_at = timezone.now()
        booking.arrived_at = timezone.now()
        booking.start_service_pin = 4321
        booking.start_pin_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        artist_client.put(
            '/artists/bookings/start_pin/verify/',
            {'booking_id': booking.booking_id, 'start_service_pin': 4321}, format='json',
        )
        booking.refresh_from_db()
        return customer_client, booking

    def test_get_completion_pin_after_service_start_returns_200(self):
        customer_client, booking = self._in_progress_booking('+919000000350', '+919000000351')
        resp = customer_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['completionPin'], booking.completion_pin)

    def test_get_completion_pin_before_service_start_returns_400(self):
        customer_client, customer = make_customer(phone_number='+919000000352')
        _, _, profile = make_artist(phone_number='+919000000353')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        resp = customer_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)

    def test_get_completion_pin_for_another_customers_booking_returns_400(self):
        _, booking = self._in_progress_booking('+919000000354', '+919000000355')
        outsider_client, _ = make_customer(phone_number='+919000000356')
        resp = outsider_client.get(self.url, {'booking_id': booking.booking_id})
        self.assertEqual(resp.status_code, 400)


# ─── Artist Verify Completion PIN ───────────────────────────────────────────────

class VerifyCompletionPinTest(TestCase):
    url = '/artists/bookings/completion_pin/verify/'

    def _make_in_progress_booking(self, artist_phone, customer_phone, pin=5678):
        artist_client, artist_user, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        customer_client, customer = make_customer(phone_number=customer_phone)
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='in_progress',
        )
        booking.completion_pin = pin
        booking.completion_pin_expiry = timezone.now() + timedelta(hours=6)
        booking.save()
        return artist_client, customer_client, booking

    def test_verify_correct_pin_completes_booking(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000360', '+919000000361')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'completed')
        self.assertIsNotNone(booking.service_completed_at)
        self.assertIsNone(booking.completion_pin)
        self.assertIsNone(booking.completion_pin_expiry)

    def test_verify_incorrect_pin_returns_400_and_does_not_complete(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000362', '+919000000363')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 1111}, format='json')
        self.assertEqual(resp.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')
        self.assertIsNone(booking.service_completed_at)
        self.assertEqual(booking.completion_pin_attempts, 1)

    def test_verify_expired_pin_returns_400(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000364', '+919000000365')
        booking.completion_pin_expiry = timezone.now() - timedelta(minutes=1)
        booking.save()
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_locks_out_after_5_failed_attempts(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000366', '+919000000367')
        for _ in range(5):
            resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 1111}, format='json')
            self.assertEqual(resp.status_code, 400)
        locked_resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(locked_resp.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status.name, 'in_progress')

    def test_verify_pin_before_service_started_returns_400(self):
        artist_client, artist_user, profile = make_artist(phone_number='+919000000368')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        _, customer = make_customer(phone_number='+919000000369')
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='confirmed',
        )
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_twice_returns_400(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000370', '+919000000371')
        first = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(first.status_code, 200)
        second = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_verify_pin_on_another_artists_booking_returns_400(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000372', '+919000000373')
        other_client, _, _ = make_artist(phone_number='+919000000374')
        resp = other_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_pin_notifies_customer(self):
        artist_client, _, booking = self._make_in_progress_booking('+919000000375', '+919000000376')
        resp = artist_client.put(self.url, {'booking_id': booking.booking_id, 'completion_pin': 5678}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Notification.objects.filter(booking_id=booking.booking_id, type='booking_completed').exists())


# ─── Payment ───────────────────────────────────────────────────────────────────

class PaymentTest(TestCase):
    initiate_url = '/customers/payments/initiate/'
    webhook_url = '/customers/payments/webhook/'
    get_all_url = '/customers/payments/get_all/'

    def _make_booking(self, customer_phone='+919000000280', artist_phone='+919000000281', price=1500):
        client, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub, price=price)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
        )
        return client, customer, profile, booking

    def test_initiate_payment_full_amount(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking()
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('gateway_order_id', resp.data['data'])
        payment = Payment.objects.get(payment_id=resp.data['data']['payment_id'])
        self.assertEqual(str(payment.amount), '1500.00')
        self.assertEqual(str(payment.commission_amount), '150.00')

    def test_initiate_payment_exceeding_remaining_due_returns_400(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000282', artist_phone='+919000000283')
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id, 'amount': '9999.00'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_webhook_marks_payment_paid(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000284', artist_phone='+919000000285')
        resp = client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        gateway_order_id = resp.data['data']['gateway_order_id']

        webhook_client = APIClient()
        webhook_resp = webhook_client.post(self.webhook_url, {
            'gateway_order_id': gateway_order_id,
            'gateway_payment_id': 'test_txn_123',
            'status': 'paid',
        }, format='json')
        self.assertEqual(webhook_resp.status_code, 200)
        payment = Payment.objects.get(gateway_order_id=gateway_order_id)
        self.assertEqual(payment.status.name, 'paid')
        self.assertIsNotNone(payment.paid_at)

    def test_webhook_unknown_order_returns_400(self):
        seed_payment_statuses()
        webhook_client = APIClient()
        resp = webhook_client.post(self.webhook_url, {
            'gateway_order_id': 'DOES-NOT-EXIST',
            'gateway_payment_id': 'x',
            'status': 'paid',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_get_all_payments_returns_own_only(self):
        seed_payment_statuses()
        client, customer, profile, booking = self._make_booking(customer_phone='+919000000286', artist_phone='+919000000287')
        client.post(self.initiate_url, {'booking_id': booking.booking_id}, format='json')
        other_client, _, _, other_booking = self._make_booking(customer_phone='+919000000288', artist_phone='+919000000289')
        other_client.post(self.initiate_url, {'booking_id': other_booking.booking_id}, format='json')

        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)


# ─── Reviews ───────────────────────────────────────────────────────────────────

class ReviewTest(TestCase):
    create_url = '/customers/reviews/create/'
    get_all_url = '/customers/reviews/get_all/'

    def _completed_booking(self, customer_phone='+919000000290', artist_phone='+919000000291'):
        client, customer = make_customer(phone_number=customer_phone)
        _, _, profile = make_artist(phone_number=artist_phone)
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='completed',
        )
        return client, customer, profile, booking

    def test_create_review_after_completed_returns_201(self):
        client, customer, profile, booking = self._completed_booking()
        resp = client.post(self.create_url, {'booking_id': booking.booking_id, 'rating': 5, 'comment': 'Great!'}, format='json')
        self.assertEqual(resp.status_code, 201)
        profile.refresh_from_db()
        self.assertEqual(profile.total_reviews, 1)
        self.assertEqual(str(profile.avg_rating), '5.00')

    def test_create_review_before_completed_returns_400(self):
        client, customer = make_customer(phone_number='+919000000292')
        _, _, profile = make_artist(phone_number='+919000000293')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking = make_booking(
            customer, profile, package, location_type,
            booking_date=next_weekday(2), start_time='10:00:00', end_time='11:00:00',
            status_name='pending',
        )
        resp = client.post(self.create_url, {'booking_id': booking.booking_id, 'rating': 4}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_review_returns_400(self):
        client, customer, profile, booking = self._completed_booking(customer_phone='+919000000294', artist_phone='+919000000295')
        client.post(self.create_url, {'booking_id': booking.booking_id, 'rating': 5}, format='json')
        resp = client.post(self.create_url, {'booking_id': booking.booking_id, 'rating': 3}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_incremental_average_rating(self):
        client1, _, profile, booking1 = self._completed_booking(customer_phone='+919000000296', artist_phone='+919000000297')
        client1.post(self.create_url, {'booking_id': booking1.booking_id, 'rating': 5}, format='json')

        client2, customer2 = make_customer(phone_number='+919000000298')
        sub = make_sub_category()
        package = make_package(profile, sub_category=sub)
        location_type = make_location_type()
        booking2 = make_booking(
            customer2, profile, package, location_type,
            booking_date=next_weekday(3), start_time='10:00:00', end_time='11:00:00',
            status_name='completed',
        )
        client2.post(self.create_url, {'booking_id': booking2.booking_id, 'rating': 3}, format='json')

        profile.refresh_from_db()
        self.assertEqual(profile.total_reviews, 2)
        self.assertEqual(str(profile.avg_rating), '4.00')

    def test_get_all_reviews_by_artist(self):
        client, customer, profile, booking = self._completed_booking(customer_phone='+919000000299', artist_phone='+919000000300')
        client.post(self.create_url, {'booking_id': booking.booking_id, 'rating': 5}, format='json')
        resp = client.get(self.get_all_url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)
