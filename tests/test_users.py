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

    def test_update_email_directly_is_refused_and_changes_nothing(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'email': 'newemail@example.com'})
        self.assertEqual(resp.status_code, 400)
        user.refresh_from_db()
        self.assertIsNone(user.email)

    def test_update_phone_directly_is_refused_and_changes_nothing(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'phone_number': '+919999999999'})
        self.assertEqual(resp.status_code, 400)
        user.refresh_from_db()
        self.assertEqual(user.phone_number, '+919876543210')

    def test_name_still_updates_when_current_contacts_are_resent(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        resp = client.put(self.url, {'name': 'Renamed', 'phone_number': '+919876543210'})
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.name, 'Renamed')

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



# ─── Verified email / phone change ────────────────────────────────────────────

from datetime import timedelta
from unittest.mock import patch


class ContactChangeTest(TestCase):
    request_url = '/users/contact/change/request/'
    verify_url = '/users/contact/change/verify/'

    def setUp(self):
        self.client_a, self.user = make_authenticated_client(phone_number='+919876543210', email='old@example.com')

    def _request(self, client=None, **payload):
        with patch('sunndari_apps.users.views.contact_change.send_otp_email') as email, \
                patch('sunndari_apps.users.views.contact_change.send_otp_sms') as sms:
            resp = (client or self.client_a).post(self.request_url, payload, format='json')
        return resp, email, sms

    def _code(self):
        self.user.refresh_from_db()
        return self.user.contact_otp

    def test_email_change_end_to_end_sends_code_to_the_new_address_only(self):
        resp, email, sms = self._request(email='new@example.com')
        self.assertEqual(resp.status_code, 200)
        email.assert_called_once()
        self.assertEqual(email.call_args[0][0], 'new@example.com')
        sms.assert_not_called()
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'old@example.com')              # nothing changed yet
        resp = self.client_a.post(self.verify_url, {'otp': str(self._code())}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertEqual(self.user.phone_number, '+919876543210')
        self.assertIsNone(self.user.contact_otp)
        self.assertIsNone(self.user.pending_email)

    def test_phone_change_end_to_end(self):
        resp, email, sms = self._request(phone_number='+919111111111')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sms.call_args[0][0], '+919111111111')
        self.client_a.post(self.verify_url, {'otp': str(self._code())}, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, '+919111111111')

    def test_code_is_single_use(self):
        self._request(email='new@example.com')
        code = str(self._code())
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': code}, format='json').status_code, 200)
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': code}, format='json').status_code, 400)

    def test_wrong_code_is_counted_and_five_burn_the_code(self):
        self._request(email='new@example.com')
        code = self._code()
        wrong = '000000' if code != 0 else '111111'
        for _ in range(4):
            self.assertEqual(self.client_a.post(self.verify_url, {'otp': wrong}, format='json').status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.contact_otp_attempts, 4)
        self.client_a.post(self.verify_url, {'otp': wrong}, format='json')
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': str(code)}, format='json').status_code, 400)  # burned
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'old@example.com')

    def test_expired_code_is_rejected(self):
        self._request(email='new@example.com')
        code = self._code()
        from django.utils import timezone
        type(self.user).objects.filter(user_id=self.user.user_id).update(contact_otp_expiry=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': str(code)}, format='json').status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'old@example.com')

    def test_verifying_without_a_pending_request_fails(self):
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': '123456'}, format='json').status_code, 400)

    def test_login_otp_cannot_be_used_to_confirm_and_vice_versa(self):
        self._request(email='new@example.com')
        contact_code = self._code()
        login_code = self.user.generate_otp()
        if login_code == contact_code:
            login_code = (login_code % 899999) + 100000
            self.user.otp = login_code
            self.user.save()
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': str(login_code)}, format='json').status_code, 400)
        self.assertEqual(self.client_a.post('/auth/phone-otp/verify/', {
            'phone_number': '+919876543210', 'otp': str(contact_code)}, format='json').status_code, 400)

    def test_requests_are_throttled_and_new_request_replaces_the_old_code(self):
        self._request(email='first@example.com')
        resp, _, _ = self._request(email='second@example.com')
        self.assertEqual(resp.status_code, 400)
        from django.utils import timezone
        type(self.user).objects.filter(user_id=self.user.user_id).update(contact_otp_requested_at=timezone.now() - timedelta(minutes=2))
        old_code = self._code()
        resp, _, _ = self._request(email='second@example.com')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.pending_email, 'second@example.com')

    def test_validation_rules(self):
        self.assertEqual(self._request()[0].status_code, 400)                                         # neither
        self.assertEqual(self._request(email='a@example.com', phone_number='+919000000001')[0].status_code, 400)   # both
        self.assertEqual(self._request(email='not-an-email')[0].status_code, 400)
        self.assertEqual(self._request(email='old@example.com')[0].status_code, 400)                  # unchanged
        self.assertEqual(self._request(phone_number='+919876543210')[0].status_code, 400)
        make_user(email='taken@example.com', phone_number='+910000000009')
        self.assertEqual(self._request(email='taken@example.com')[0].status_code, 400)
        self.assertEqual(self._request(phone_number='+910000000009')[0].status_code, 400)
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': '12ab56'}, format='json').status_code, 400)

    def test_contact_taken_between_request_and_verify_is_rejected(self):
        self._request(email='race@example.com')
        code = self._code()
        make_user(email='race@example.com', phone_number='+910000000010')
        self.assertEqual(self.client_a.post(self.verify_url, {'otp': str(code)}, format='json').status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'old@example.com')

    def test_users_cannot_confirm_each_others_changes_and_auth_required(self):
        self._request(email='new@example.com')
        code = self._code()
        other_client, other = make_authenticated_client(phone_number='+919000000777')
        self.assertEqual(other_client.post(self.verify_url, {'otp': str(code)}, format='json').status_code, 400)
        self.assertEqual(APIClient().post(self.request_url, {'email': 'x@example.com'}, format='json').status_code, 401)
        self.assertEqual(APIClient().post(self.verify_url, {'otp': str(code)}, format='json').status_code, 401)

    def test_change_notifies_the_user_and_old_contact_no_longer_logs_in(self):
        from sunndari_apps.notifications.models.notification import Notification
        self.user.set_password('secret-pass-1')
        self.user.save()
        self._request(email='new@example.com')
        self.client_a.post(self.verify_url, {'otp': str(self._code())}, format='json')
        self.assertTrue(Notification.objects.filter(user_id=self.user.user_id, type='contact_changed').exists())
        self.assertEqual(APIClient().post('/auth/login/', {'username': 'old@example.com', 'password': 'secret-pass-1'}).status_code, 401)
        self.assertEqual(APIClient().post('/auth/login/', {'username': 'new@example.com', 'password': 'secret-pass-1'}).status_code, 200)
