import datetime
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token, generate_refresh_token


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


# ─── Phone OTP Request ────────────────────────────────────────────────────────

class PhoneOTPRequestTest(TestCase):
    url = '/auth/phone-otp/request/'

    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_new_user_with_role_creates_user_and_returns_200(self, mock_sms):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'role': 'customer'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertTrue(User.objects.filter(phone_number='+919876543210').exists())
        mock_sms.assert_called_once()

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_existing_user_without_role_returns_200(self, mock_sms):
        make_user(phone_number='+919876543210')
        resp = self.client.post(self.url, {'phone_number': '+919876543210'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])

    def test_unknown_user_without_role_returns_404(self):
        resp = self.client.post(self.url, {'phone_number': '+910000000000'})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.data['status'])

    def test_missing_phone_returns_400(self):
        resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 400)

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_locked_account_returns_403(self, mock_sms):
        user = make_user(phone_number='+919876543210')
        user.lockout_until = timezone.now() + timezone.timedelta(minutes=30)
        user.save()
        resp = self.client.post(self.url, {'phone_number': '+919876543210'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.data['status'])
        mock_sms.assert_not_called()

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_otp_is_generated_and_stored(self, mock_sms):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'role': 'customer'})
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone_number='+919876543210')
        self.assertIsNotNone(user.otp)
        self.assertIsNotNone(user.otp_expiry)


# ─── Phone OTP Verify ─────────────────────────────────────────────────────────

class PhoneOTPVerifyTest(TestCase):
    url = '/auth/phone-otp/verify/'

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(phone_number='+919876543210')
        self.user.otp = 123456
        self.user.otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
        self.user.save()

    def test_correct_otp_returns_200_with_tokens(self):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '123456'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)
        self.assertEqual(data['phone_number'], '+919876543210')

    def test_wrong_otp_returns_400(self):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '999999'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_expired_otp_returns_400(self):
        self.user.otp_expiry = timezone.now() - timezone.timedelta(minutes=1)
        self.user.save()
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '123456'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_unknown_user_returns_404(self):
        resp = self.client.post(self.url, {'phone_number': '+910000000000', 'otp': '123456'})
        self.assertEqual(resp.status_code, 404)

    def test_locked_account_returns_403(self):
        self.user.lockout_until = timezone.now() + timezone.timedelta(minutes=30)
        self.user.save()
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '123456'})
        self.assertEqual(resp.status_code, 403)

    def test_invalid_otp_format_returns_400(self):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': 'abc123'})
        self.assertEqual(resp.status_code, 400)

    def test_otp_too_short_returns_400(self):
        resp = self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '1234'})
        self.assertEqual(resp.status_code, 400)

    def test_five_wrong_attempts_trigger_lockout(self):
        for _ in range(5):
            self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '000000'})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.lockout_until)
        self.assertTrue(self.user.lockout_until > timezone.now())

    def test_otp_cleared_after_successful_verify(self):
        self.client.post(self.url, {'phone_number': '+919876543210', 'otp': '123456'})
        self.user.refresh_from_db()
        self.assertIsNone(self.user.otp)
        self.assertIsNone(self.user.otp_expiry)


# ─── Email OTP Request ────────────────────────────────────────────────────────

class EmailOTPRequestTest(TestCase):
    url = '/auth/email-otp/request/'

    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.send_otp_email')
    def test_new_user_with_role_creates_user_and_returns_200(self, mock_email):
        resp = self.client.post(self.url, {'email': 'new@example.com', 'role': 'customer'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.objects.filter(email='new@example.com').exists())
        mock_email.assert_called_once()

    @patch('sunndari_apps.authentication.views.send_otp_email')
    def test_existing_user_without_role_returns_200(self, mock_email):
        make_user(email='existing@example.com')
        resp = self.client.post(self.url, {'email': 'existing@example.com'})
        self.assertEqual(resp.status_code, 200)

    def test_unknown_user_without_role_returns_404(self):
        resp = self.client.post(self.url, {'email': 'nobody@example.com'})
        self.assertEqual(resp.status_code, 404)

    def test_invalid_email_format_returns_400(self):
        resp = self.client.post(self.url, {'email': 'not-an-email', 'role': 'customer'})
        self.assertEqual(resp.status_code, 400)

    @patch('sunndari_apps.authentication.views.send_otp_email')
    def test_locked_account_returns_403(self, mock_email):
        user = make_user(email='locked@example.com')
        user.lockout_until = timezone.now() + timezone.timedelta(minutes=30)
        user.save()
        resp = self.client.post(self.url, {'email': 'locked@example.com'})
        self.assertEqual(resp.status_code, 403)
        mock_email.assert_not_called()


# ─── Email OTP Verify ─────────────────────────────────────────────────────────

class EmailOTPVerifyTest(TestCase):
    url = '/auth/email-otp/verify/'

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email='test@example.com')
        self.user.otp = 654321
        self.user.otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
        self.user.save()

    def test_correct_otp_returns_200_with_tokens(self):
        resp = self.client.post(self.url, {'email': 'test@example.com', 'otp': '654321'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)

    def test_wrong_otp_returns_400(self):
        resp = self.client.post(self.url, {'email': 'test@example.com', 'otp': '000000'})
        self.assertEqual(resp.status_code, 400)

    def test_expired_otp_returns_400(self):
        self.user.otp_expiry = timezone.now() - timezone.timedelta(seconds=1)
        self.user.save()
        resp = self.client.post(self.url, {'email': 'test@example.com', 'otp': '654321'})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_email_returns_404(self):
        resp = self.client.post(self.url, {'email': 'ghost@example.com', 'otp': '654321'})
        self.assertEqual(resp.status_code, 404)


# ─── Password Register ────────────────────────────────────────────────────────

class RegisterTest(TestCase):
    url = '/auth/register/'

    def setUp(self):
        self.client = APIClient()

    def test_register_with_email_returns_200_with_tokens(self):
        resp = self.client.post(self.url, {
            'name': 'Alice',
            'email': 'alice@example.com',
            'password': 'securepass123',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        data = resp.data['data']
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)
        self.assertEqual(data['email'], 'alice@example.com')

    def test_register_with_phone_returns_200(self):
        resp = self.client.post(self.url, {
            'name': 'Bob',
            'phone_number': '+911234567890',
            'password': 'securepass123',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['phone_number'], '+911234567890')

    def test_register_without_email_or_phone_returns_400(self):
        resp = self.client.post(self.url, {
            'name': 'Nobody',
            'password': 'securepass123',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_register_password_too_short_returns_400(self):
        resp = self.client.post(self.url, {
            'name': 'Short',
            'email': 'short@example.com',
            'password': 'abc',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_duplicate_email_returns_400(self):
        make_user(email='dup@example.com')
        resp = self.client.post(self.url, {
            'name': 'Duplicate',
            'email': 'dup@example.com',
            'password': 'securepass123',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_register_duplicate_phone_returns_400(self):
        make_user(phone_number='+911111111111')
        resp = self.client.post(self.url, {
            'name': 'Duplicate',
            'phone_number': '+911111111111',
            'password': 'securepass123',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_register_password_is_hashed_in_db(self):
        self.client.post(self.url, {
            'name': 'Hashed',
            'email': 'hashed@example.com',
            'password': 'plaintext123',
            'role': 'customer',
        })
        user = User.objects.get(email='hashed@example.com')
        self.assertNotEqual(user.password, 'plaintext123')
        self.assertTrue(user.check_password('plaintext123'))


# ─── Password Login ───────────────────────────────────────────────────────────

class LoginTest(TestCase):
    url = '/auth/login/'

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email='login@example.com', phone_number='+919999999999')
        self.user.set_password('mypassword123')
        self.user.save()

    def test_login_with_email_returns_200_with_tokens(self):
        resp = self.client.post(self.url, {'username': 'login@example.com', 'password': 'mypassword123'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertIn('access_token', resp.data['data'])
        self.assertIn('refresh_token', resp.data['data'])

    def test_login_with_phone_returns_200(self):
        resp = self.client.post(self.url, {'username': '+919999999999', 'password': 'mypassword123'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])

    def test_login_wrong_password_returns_401(self):
        resp = self.client.post(self.url, {'username': 'login@example.com', 'password': 'wrongpass'})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.data['status'])

    def test_login_unknown_user_returns_401(self):
        resp = self.client.post(self.url, {'username': 'ghost@example.com', 'password': 'anything'})
        self.assertEqual(resp.status_code, 401)

    def test_login_missing_password_returns_400(self):
        resp = self.client.post(self.url, {'username': 'login@example.com'})
        self.assertEqual(resp.status_code, 400)


# ─── Google Auth ──────────────────────────────────────────────────────────────

MOCK_GOOGLE_DATA = {
    'google_id': 'google_uid_12345',
    'email': 'google@example.com',
    'name': 'Google User',
}


class GoogleAuthTest(TestCase):
    url = '/auth/google/'

    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value=MOCK_GOOGLE_DATA)
    def test_new_user_with_role_creates_user_and_returns_200(self, mock_google):
        resp = self.client.post(self.url, {'id_token': 'fake_token', 'role': 'customer'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertTrue(User.objects.filter(google_id='google_uid_12345').exists())

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value=MOCK_GOOGLE_DATA)
    def test_existing_user_by_google_id_returns_200_without_creating_duplicate(self, mock_google):
        make_user(email='google@example.com', google_id='google_uid_12345')
        resp = self.client.post(self.url, {'id_token': 'fake_token'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(google_id='google_uid_12345').count(), 1)

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value=MOCK_GOOGLE_DATA)
    def test_existing_user_by_email_links_google_id(self, mock_google):
        user = make_user(email='google@example.com', google_id=None)
        resp = self.client.post(self.url, {'id_token': 'fake_token'})
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.google_id, 'google_uid_12345')

    @patch('sunndari_apps.authentication.views.verify_google_token', side_effect=Exception('Invalid token'))
    def test_invalid_google_token_returns_401(self, mock_google):
        resp = self.client.post(self.url, {'id_token': 'bad_token', 'role': 'customer'})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.data['status'])

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value=MOCK_GOOGLE_DATA)
    def test_new_user_without_role_returns_400(self, mock_google):
        resp = self.client.post(self.url, {'id_token': 'fake_token'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data['status'])

    def test_missing_id_token_returns_400(self):
        resp = self.client.post(self.url, {'role': 'customer'})
        self.assertEqual(resp.status_code, 400)


# ─── Token Refresh ────────────────────────────────────────────────────────────

class TokenRefreshTest(TestCase):
    url = '/auth/token/refresh/'

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(phone_number='+919876543210')
        self.refresh_token = generate_refresh_token(self.user)
        self.user.refresh_token = self.refresh_token
        self.user.save()

    def test_valid_refresh_token_returns_200_with_new_tokens(self):
        resp = self.client.post(self.url, {'refresh_token': self.refresh_token})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertIn('access_token', resp.data['data'])
        self.assertIn('refresh_token', resp.data['data'])

    def test_invalid_jwt_returns_401(self):
        resp = self.client.post(self.url, {'refresh_token': 'not.a.jwt'})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.data['status'])

    def test_token_not_stored_in_db_returns_401(self):
        other_token = generate_refresh_token(self.user)
        # Store a different token in DB than what we pass
        self.user.refresh_token = 'something_else'
        self.user.save()
        resp = self.client.post(self.url, {'refresh_token': other_token})
        self.assertEqual(resp.status_code, 401)

    def test_missing_refresh_token_returns_400(self):
        resp = self.client.post(self.url, {})
        self.assertEqual(resp.status_code, 400)


# ─── JWT Authentication Middleware ────────────────────────────────────────────

class JWTAuthenticationTest(TestCase):
    profile_url = '/users/profile/get/'

    def test_no_auth_header_returns_401(self):
        client = APIClient()
        resp = client.get(self.profile_url)
        self.assertEqual(resp.status_code, 401)

    def test_invalid_token_returns_401(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer invalid.token.here')
        resp = client.get(self.profile_url)
        self.assertEqual(resp.status_code, 401)

    def test_valid_token_allows_access(self):
        client, user = make_authenticated_client(phone_number='+919876543210')
        resp = client.get(self.profile_url, {'user_id': user.user_id})
        self.assertEqual(resp.status_code, 200)

    def test_token_mismatch_with_db_returns_401(self):
        user = make_user(phone_number='+919876543210')
        token = generate_jwt_token(user)
        user.access_token = 'different_token_stored_in_db'
        user.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resp = client.get(self.profile_url)
        self.assertEqual(resp.status_code, 401)

    def test_expired_token_returns_401(self):
        import jwt
        from django.conf import settings
        user = make_user(phone_number='+919876543210')
        payload = {
            'user_id': user.user_id,
            'role': user.role,
            'exp': datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1),
            'iat': datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
        }
        expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
        user.access_token = expired_token
        user.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {expired_token}')
        resp = client.get(self.profile_url)
        self.assertEqual(resp.status_code, 401)


# ─── Artist Role — Auth Flows ─────────────────────────────────────────────────

class ArtistPhoneOTPTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_artist_phone_otp_request_creates_artist_user(self, mock_sms):
        resp = self.client.post('/auth/phone-otp/request/', {
            'phone_number': '+919000000001',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone_number='+919000000001')
        self.assertEqual(user.role, 'artist')

    @patch('sunndari_apps.authentication.views.send_otp_sms')
    def test_artist_phone_otp_verify_issues_token_with_artist_role(self, mock_sms):
        self.client.post('/auth/phone-otp/request/', {
            'phone_number': '+919000000001',
            'role': 'artist',
        })
        user = User.objects.get(phone_number='+919000000001')
        otp = str(user.otp)
        resp = self.client.post('/auth/phone-otp/verify/', {
            'phone_number': '+919000000001',
            'otp': otp,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')
        self.assertIn('access_token', resp.data['data'])
        self.assertIn('refresh_token', resp.data['data'])


class ArtistEmailOTPTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.send_otp_email')
    def test_artist_email_otp_request_creates_artist_user(self, mock_email):
        resp = self.client.post('/auth/email-otp/request/', {
            'email': 'artist@example.com',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(email='artist@example.com')
        self.assertEqual(user.role, 'artist')

    @patch('sunndari_apps.authentication.views.send_otp_email')
    def test_artist_email_otp_verify_issues_token_with_artist_role(self, mock_email):
        self.client.post('/auth/email-otp/request/', {
            'email': 'artist@example.com',
            'role': 'artist',
        })
        user = User.objects.get(email='artist@example.com')
        otp = str(user.otp)
        resp = self.client.post('/auth/email-otp/verify/', {
            'email': 'artist@example.com',
            'otp': otp,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')
        self.assertIn('access_token', resp.data['data'])


class ArtistPasswordAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_artist_register_with_email_returns_200(self):
        resp = self.client.post('/auth/register/', {
            'name': 'Priya Artist',
            'email': 'priya@artist.com',
            'password': 'securepass123',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')
        self.assertIn('access_token', resp.data['data'])
        self.assertIn('refresh_token', resp.data['data'])
        self.assertEqual(User.objects.get(email='priya@artist.com').role, 'artist')

    def test_artist_login_with_email_returns_200(self):
        self.client.post('/auth/register/', {
            'name': 'Priya Artist',
            'email': 'priya@artist.com',
            'password': 'securepass123',
            'role': 'artist',
        })
        resp = self.client.post('/auth/login/', {
            'username': 'priya@artist.com',
            'password': 'securepass123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')

    def test_artist_register_with_phone_returns_200(self):
        resp = self.client.post('/auth/register/', {
            'name': 'Rahul Artist',
            'phone_number': '+918888888888',
            'password': 'securepass123',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')

    def test_artist_login_with_phone_returns_200(self):
        self.client.post('/auth/register/', {
            'name': 'Rahul Artist',
            'phone_number': '+918888888888',
            'password': 'securepass123',
            'role': 'artist',
        })
        resp = self.client.post('/auth/login/', {
            'username': '+918888888888',
            'password': 'securepass123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')


class ArtistGoogleAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value={
        'google_id': 'artist_google_uid',
        'email': 'artist.google@example.com',
        'name': 'Google Artist',
    })
    def test_artist_google_first_login_creates_artist_user(self, mock_google):
        resp = self.client.post('/auth/google/', {
            'id_token': 'fake_token',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')
        self.assertEqual(User.objects.get(google_id='artist_google_uid').role, 'artist')

    @patch('sunndari_apps.authentication.views.verify_google_token', return_value={
        'google_id': 'artist_google_uid',
        'email': 'artist.google@example.com',
        'name': 'Google Artist',
    })
    def test_artist_google_subsequent_login_returns_200(self, mock_google):
        make_user(email='artist.google@example.com', google_id='artist_google_uid', role='artist')
        resp = self.client.post('/auth/google/', {'id_token': 'fake_token'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')


class ArtistProfileTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(phone_number='+919000000001', role='artist', name='Artist User')
        token = generate_jwt_token(self.user)
        self.user.access_token = token
        self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_artist_get_profile_returns_artist_role(self):
        resp = self.client.get('/users/profile/get/', {'user_id': self.user.user_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')

    def test_artist_update_name_returns_200(self):
        resp = self.client.put('/users/profile/update/', {'name': 'New Artist Name'})
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, 'New Artist Name')

    def test_artist_token_refresh_returns_200(self):
        refresh_token = generate_refresh_token(self.user)
        self.user.refresh_token = refresh_token
        self.user.save()
        resp = self.client.post('/auth/token/refresh/', {'refresh_token': refresh_token})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['role'], 'artist')
