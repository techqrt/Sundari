from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_user(phone_number='+919876543210'):
    return User.objects.create(phone_number=phone_number, role='customer', name='Test User')


def make_authenticated_client(phone_number='+919876543210'):
    user = make_user(phone_number=phone_number)
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_category(name='Hair', description=None):
    return ServiceCategory.objects.create(name=name, description=description)


def make_sub_category(category, name='Haircut', description='Precision cut'):
    return ServiceSubCategory.objects.create(category=category, name=name, description=description)


def make_location_type(name='Home Visit', description='At home'):
    return LocationType.objects.create(name=name, description=description)


def seed_statuses():
    BookingStatus.objects.get_or_create(name='pending', defaults={'description': 'Awaiting confirmation'})
    BookingStatus.objects.get_or_create(name='confirmed', defaults={'description': 'Confirmed'})
    PaymentStatus.objects.get_or_create(name='paid', defaults={'description': 'Payment received'})
    PaymentStatus.objects.get_or_create(name='pending', defaults={'description': 'Awaiting payment'})
    ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
    ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Awaiting review'})


# ─── Service Category ─────────────────────────────────────────────────────────

class ServiceCategoryGetTest(TestCase):
    url = '/core/service-category/get/'

    def test_get_returns_200_with_data(self):
        client = make_authenticated_client()
        cat = make_category(name='Skin & Facial')
        resp = client.get(self.url, {'category_id': cat.category_id})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertEqual(resp.data['data']['name'], 'Skin & Facial')

    def test_get_returns_camelcase_keys(self):
        client = make_authenticated_client()
        cat = make_category()
        resp = client.get(self.url, {'category_id': cat.category_id})
        data = resp.data['data']
        self.assertIn('categoryId', data)
        self.assertIn('isActive', data)
        self.assertIn('createdAt', data)

    def test_get_nonexistent_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url, {'category_id': 99999})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_get_missing_id_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url, {'category_id': 1})
        self.assertEqual(resp.status_code, 401)


class ServiceCategoryGetAllTest(TestCase):
    url = '/core/service-category/get_all/'

    def test_get_all_returns_200_with_pagination(self):
        client = make_authenticated_client()
        make_category(name='Bridal')
        make_category(name='Nail Art')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertIn('data', data)
        self.assertIn('presentPage', data)
        self.assertIn('totalPage', data)
        self.assertEqual(len(data['data']), 2)

    def test_get_all_empty_returns_200(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'], [])

    def test_get_all_search_filters_results(self):
        client = make_authenticated_client()
        make_category(name='Hair')
        make_category(name='Nail Art')
        resp = client.get(self.url, {'search_key': 'hair'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)
        self.assertEqual(resp.data['data']['data'][0]['name'], 'Hair')

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Service Sub-Category ─────────────────────────────────────────────────────

class ServiceSubCategoryGetTest(TestCase):
    url = '/core/service-sub-category/get/'

    def test_get_returns_200_with_data(self):
        client = make_authenticated_client()
        cat = make_category(name='Hair')
        sub = make_sub_category(cat, name='Keratin Treatment')
        resp = client.get(self.url, {'sub_category_id': sub.sub_category_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['name'], 'Keratin Treatment')

    def test_get_returns_category_id(self):
        client = make_authenticated_client()
        cat = make_category(name='Makeup')
        sub = make_sub_category(cat, name='HD Makeup')
        resp = client.get(self.url, {'sub_category_id': sub.sub_category_id})
        self.assertEqual(resp.data['data']['categoryId'], cat.category_id)

    def test_get_returns_camelcase_keys(self):
        client = make_authenticated_client()
        cat = make_category()
        sub = make_sub_category(cat)
        resp = client.get(self.url, {'sub_category_id': sub.sub_category_id})
        data = resp.data['data']
        self.assertIn('subCategoryId', data)
        self.assertIn('categoryId', data)
        self.assertIn('isActive', data)

    def test_get_nonexistent_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url, {'sub_category_id': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_get_missing_id_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url, {'sub_category_id': 1})
        self.assertEqual(resp.status_code, 401)


class ServiceSubCategoryGetAllTest(TestCase):
    url = '/core/service-sub-category/get_all/'

    def test_get_all_returns_200_with_pagination(self):
        client = make_authenticated_client()
        cat = make_category(name='Waxing')
        make_sub_category(cat, name='Full Body Wax')
        make_sub_category(cat, name='Underarm Wax')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 2)

    def test_get_all_filter_by_category_id(self):
        client = make_authenticated_client()
        cat1 = make_category(name='Hair')
        cat2 = make_category(name='Skin')
        make_sub_category(cat1, name='Haircut')
        make_sub_category(cat2, name='Facial')
        resp = client.get(self.url, {'filter_key': 'categoryId', 'filter_value': str(cat1.category_id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)
        self.assertEqual(resp.data['data']['data'][0]['name'], 'Haircut')

    def test_get_all_empty_returns_200(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'], [])

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Location Type ────────────────────────────────────────────────────────────

class LocationTypeGetTest(TestCase):
    url = '/core/location-type/get/'

    def test_get_returns_200_with_data(self):
        client = make_authenticated_client()
        lt = make_location_type(name='In-Salon')
        resp = client.get(self.url, {'location_type_id': lt.location_type_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['name'], 'In-Salon')

    def test_get_returns_camelcase_keys(self):
        client = make_authenticated_client()
        lt = make_location_type()
        resp = client.get(self.url, {'location_type_id': lt.location_type_id})
        data = resp.data['data']
        self.assertIn('locationTypeId', data)
        self.assertIn('isActive', data)

    def test_get_nonexistent_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url, {'location_type_id': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_get_missing_id_returns_400(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url, {'location_type_id': 1})
        self.assertEqual(resp.status_code, 401)


class LocationTypeGetAllTest(TestCase):
    url = '/core/location-type/get_all/'

    def test_get_all_returns_200(self):
        client = make_authenticated_client()
        make_location_type(name='Home Visit')
        make_location_type(name='In-Salon')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 2)

    def test_get_all_empty_returns_200(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'], [])

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Booking Status ───────────────────────────────────────────────────────────

class BookingStatusGetAllTest(TestCase):
    url = '/core/booking-status/get_all/'

    def test_get_all_returns_200(self):
        client = make_authenticated_client()
        seed_statuses()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)

    def test_get_all_returns_camelcase_keys(self):
        client = make_authenticated_client()
        seed_statuses()
        resp = client.get(self.url)
        first = resp.data['data'][0]
        self.assertIn('statusId', first)
        self.assertIn('name', first)
        self.assertIn('description', first)

    def test_get_all_empty_returns_200_with_empty_list(self):
        client = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data'], [])

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Payment Status ───────────────────────────────────────────────────────────

class PaymentStatusGetAllTest(TestCase):
    url = '/core/payment-status/get_all/'

    def test_get_all_returns_200(self):
        client = make_authenticated_client()
        seed_statuses()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Approval Status ──────────────────────────────────────────────────────────

class ApprovalStatusGetAllTest(TestCase):
    url = '/core/approval-status/get_all/'

    def test_get_all_returns_200(self):
        client = make_authenticated_client()
        seed_statuses()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)

    def test_get_all_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)


# ─── Seed Command Integration ─────────────────────────────────────────────────

class SeedCoreCommandTest(TestCase):

    def test_seed_creates_all_categories(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertEqual(ServiceCategory.objects.count(), 10)

    def test_seed_creates_sub_categories(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertGreaterEqual(ServiceSubCategory.objects.count(), 50)

    def test_seed_creates_location_types(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertEqual(LocationType.objects.count(), 3)

    def test_seed_creates_booking_statuses(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertEqual(BookingStatus.objects.count(), 6)

    def test_seed_creates_payment_statuses(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertEqual(PaymentStatus.objects.count(), 5)

    def test_seed_creates_approval_statuses(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        self.assertEqual(ApprovalStatus.objects.count(), 4)

    def test_seed_is_idempotent(self):
        from django.core.management import call_command
        call_command('seed_core', verbosity=0)
        call_command('seed_core', verbosity=0)
        self.assertEqual(ServiceCategory.objects.count(), 10)
        self.assertEqual(LocationType.objects.count(), 3)
