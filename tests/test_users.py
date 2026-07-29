from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.users.models.customer_address import CustomerAddress


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_user(phone_number=None, email=None, role='customer', name='Test User', **kwargs):
    return User.objects.create(
        phone_number=phone_number,
        email=email,
        role=role,
        name=name,
        **kwargs
    )


def make_authenticated_client(user=None, **user_kwargs):
    if user is None:
        user = make_user(**user_kwargs)
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client, user


def make_address(user, address_line_1='123 Main St', city='Mumbai', pin_code='400001', is_default=False):
    obj = CustomerAddress()
    address_id = obj.create(
        user_id=user.user_id,
        address_line_1=address_line_1,
        city=city,
        pin_code=pin_code,
        is_default=is_default,
    )
    return address_id


# ─── User Profile ─────────────────────────────────────────────────────────────

class UserProfileGetTest(TestCase):
    url = '/users/profile/get/'

    def test_get_own_profile_by_user_id(self):
        client, user = make_authenticated_client(phone_number='+919876543210', name='Rayyan')
        resp = client.get(self.url, {'user_id': user.user_id})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertEqual(data['name'], 'Rayyan')
        self.assertEqual(data['phoneNumber'], '+919876543210')

    def test_get_another_users_profile_by_user_id(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        other = make_user(phone_number='+910000000002', name='Other User')
        resp = client.get(self.url, {'user_id': other.user_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['name'], 'Other User')

    def test_get_profile_missing_user_id_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_get_profile_nonexistent_user_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.url, {'user_id': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_get_profile_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url, {'user_id': 1})
        self.assertEqual(resp.status_code, 401)

    def test_get_profile_returns_camelcase_keys(self):
        client, user = make_authenticated_client(
            phone_number='+919876543210',
            email='test@example.com'
        )
        resp = client.get(self.url, {'user_id': user.user_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertIn('userId', data)
        self.assertIn('phoneNumber', data)
        self.assertIn('createdAt', data)


class UserProfileUpdateTest(TestCase):
    url = '/users/profile/update/'

    def test_update_name_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919876543210', name='Old Name')
        resp = client.put(self.url, {'name': 'New Name'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        user.refresh_from_db()
        self.assertEqual(user.name, 'New Name')

    def test_update_email_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'email': 'newemail@example.com'})
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, 'newemail@example.com')

    def test_update_unauthenticated_returns_403(self):
        client = APIClient()
        resp = client.put(self.url, {'name': 'Hacker'})
        self.assertEqual(resp.status_code, 401)

    def test_update_duplicate_email_returns_400(self):
        make_user(email='taken@example.com', phone_number='+910000000001')
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'email': 'taken@example.com'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_update_duplicate_phone_returns_400(self):
        make_user(phone_number='+911111111111')
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'phone_number': '+911111111111'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_update_same_email_on_own_account_returns_200(self):
        client, _ = make_authenticated_client(
            phone_number='+919876543210',
            email='own@example.com'
        )
        resp = client.put(self.url, {'email': 'own@example.com'})
        self.assertEqual(resp.status_code, 200)


# ─── Customer Address Create ──────────────────────────────────────────────────

class AddressCreateTest(TestCase):
    url = '/users/address/create/'

    def test_create_address_returns_201_with_address_id(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.post(self.url, {
            'address_line_1': '123 Main St',
            'city': 'Mumbai',
            'pin_code': '400001',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['status'])
        self.assertIn('address_id', resp.data['data'])

    def test_create_address_is_stored_in_db(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        client.post(self.url, {
            'address_line_1': '456 Park Ave',
            'city': 'Delhi',
            'pin_code': '110001',
        })
        self.assertEqual(CustomerAddress.objects.filter(user_id=user.user_id).count(), 1)

    def test_create_default_address_clears_previous_default(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        make_address(user, address_line_1='Old Default', is_default=True)
        client.post(self.url, {
            'address_line_1': 'New Default',
            'city': 'Pune',
            'pin_code': '411001',
            'is_default': True,
        })
        defaults = CustomerAddress.objects.filter(user_id=user.user_id, is_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().address_line_1, 'New Default')

    def test_create_sixth_address_returns_400(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        for i in range(5):
            make_address(user, address_line_1=f'Address {i}', city='City', pin_code='000000')
        resp = client.post(self.url, {
            'address_line_1': 'Sixth Address',
            'city': 'Mumbai',
            'pin_code': '400001',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_create_unauthenticated_returns_403(self):
        client = APIClient()
        resp = client.post(self.url, {
            'address_line_1': '123 Main St',
            'city': 'Mumbai',
            'pin_code': '400001',
        })
        self.assertEqual(resp.status_code, 401)

    def test_create_missing_required_field_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.post(self.url, {'city': 'Mumbai', 'pin_code': '400001'})
        self.assertEqual(resp.status_code, 400)


# ─── Customer Address Get ─────────────────────────────────────────────────────

class AddressGetTest(TestCase):
    url = '/users/address/get/'

    def test_get_own_address_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        address_id = make_address(user, city='Chennai')
        resp = client.get(self.url, {'address_id': address_id})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertEqual(resp.data['data']['city'], 'Chennai')

    def test_get_returns_camelcase_keys(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        address_id = make_address(user)
        resp = client.get(self.url, {'address_id': address_id})
        data = resp.data['data']
        self.assertIn('addressId', data)
        self.assertIn('addressLine1', data)
        self.assertIn('pinCode', data)
        self.assertIn('isDefault', data)

    def test_get_another_users_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        user2 = make_user(phone_number='+910000000002')
        address_id = make_address(user2, city='Kolkata')
        resp = client.get(self.url, {'address_id': address_id})
        self.assertEqual(resp.status_code, 400)

    def test_get_nonexistent_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.url, {'address_id': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_get_missing_address_id_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 400)


# ─── Customer Address Update ──────────────────────────────────────────────────

class AddressUpdateTest(TestCase):
    url = '/users/address/update/'

    def test_update_city_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        address_id = make_address(user, city='Mumbai')
        resp = client.put(self.url, {'address_id': address_id, 'city': 'Bangalore'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        addr = CustomerAddress.objects.get(address_id=address_id)
        self.assertEqual(addr.city, 'Bangalore')

    def test_update_sets_new_default_and_clears_old(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        old_id = make_address(user, address_line_1='Old', is_default=True)
        new_id = make_address(user, address_line_1='New', is_default=False)
        client.put(self.url, {'address_id': new_id, 'is_default': True})
        self.assertFalse(CustomerAddress.objects.get(address_id=old_id).is_default)
        self.assertTrue(CustomerAddress.objects.get(address_id=new_id).is_default)

    def test_update_another_users_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        user2 = make_user(phone_number='+910000000002')
        address_id = make_address(user2)
        resp = client.put(self.url, {'address_id': address_id, 'city': 'Hyderabad'})
        self.assertEqual(resp.status_code, 400)

    def test_update_nonexistent_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'address_id': 99999, 'city': 'Nowhere'})
        self.assertEqual(resp.status_code, 400)


# ─── Customer Address Delete ──────────────────────────────────────────────────

class AddressDeleteTest(TestCase):
    url = '/users/address/delete/'

    def test_delete_own_address_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        address_id = make_address(user)
        resp = client.delete(f'{self.url}?address_id={address_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertFalse(CustomerAddress.objects.filter(address_id=address_id).exists())

    def test_delete_another_users_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        user2 = make_user(phone_number='+910000000002')
        address_id = make_address(user2)
        resp = client.delete(f'{self.url}?address_id={address_id}')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(CustomerAddress.objects.filter(address_id=address_id).exists())

    def test_delete_nonexistent_address_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.delete(f'{self.url}?address_id=99999')
        self.assertEqual(resp.status_code, 400)


# ─── Customer Address Get All ─────────────────────────────────────────────────

class AddressGetAllTest(TestCase):
    url = '/users/address/get_all/'

    def test_get_all_returns_200_with_pagination(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        make_address(user, address_line_1='Addr 1', city='Mumbai')
        make_address(user, address_line_1='Addr 2', city='Delhi')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertIn('data', data)
        self.assertIn('presentPage', data)
        self.assertIn('totalPage', data)
        self.assertEqual(len(data['data']), 2)

    def test_get_all_only_returns_own_addresses(self):
        client, user1 = make_authenticated_client(phone_number='+919876543210')
        user2 = make_user(phone_number='+910000000002')
        make_address(user1, address_line_1='Mine')
        make_address(user2, address_line_1='Theirs')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_get_all_empty_returns_200_with_empty_list(self):
        client, _ = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['data'], [])

    def test_get_all_unauthenticated_returns_403(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)
