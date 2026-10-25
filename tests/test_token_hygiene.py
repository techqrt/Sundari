import jwt
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token, generate_refresh_token

from tests.test_customers import make_customer


class TokenHygieneTest(TestCase):

    def setUp(self):
        self.client, self.user = make_customer(phone_number='+919300009001')

    def _call(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client.get('/users/address/get_all/').status_code

    def test_tokens_issued_in_the_same_second_are_still_different(self):
        self.assertNotEqual(generate_jwt_token(self.user), generate_jwt_token(self.user))
        self.assertNotEqual(generate_refresh_token(self.user), generate_refresh_token(self.user))

    def test_a_new_sign_in_ends_the_old_session_even_within_the_same_second(self):
        old = self.user.access_token
        new = generate_jwt_token(self.user)
        User.objects.filter(pk=self.user.pk).update(access_token=new)
        self.assertEqual(self._call(old), 401)
        self.assertEqual(self._call(new), 200)

    def test_a_refresh_token_is_single_use_even_when_used_immediately(self):
        refresh = generate_refresh_token(self.user)
        User.objects.filter(pk=self.user.pk).update(refresh_token=refresh)
        first = APIClient().post('/auth/token/refresh/', {'refresh_token': refresh}, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.data['data']['refresh_token'], refresh)
        again = APIClient().post('/auth/token/refresh/', {'refresh_token': refresh}, format='json')
        self.assertEqual(again.status_code, 401)                                    # replay of the used token

    def test_a_refresh_token_cannot_authenticate_a_request_even_if_stored_as_the_access_token(self):
        refresh = generate_refresh_token(self.user)
        User.objects.filter(pk=self.user.pk).update(access_token=refresh, refresh_token=refresh)
        self.assertEqual(self._call(refresh), 401)

    def test_access_tokens_declare_their_type_and_old_untyped_ones_still_work(self):
        payload = jwt.decode(generate_jwt_token(self.user), settings.SECRET_KEY, algorithms=['HS256'])
        self.assertEqual(payload['type'], 'access')
        legacy = jwt.encode({k: v for k, v in payload.items() if k not in ('type', 'jti')}, settings.SECRET_KEY, algorithm='HS256')
        User.objects.filter(pk=self.user.pk).update(access_token=legacy)
        self.assertEqual(self._call(legacy), 200)
