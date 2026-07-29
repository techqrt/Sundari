import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from sunndari_apps.activity_log.middlewares.log_middleware import local
from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import get_user_info_from_db
from sunndari.constants import Constants


class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="api"'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed(Constants.access_token_expired)
        except jwt.InvalidTokenError:
            raise AuthenticationFailed(Constants.invalid_access_token)

        user_info = get_user_info_from_db(user_id=payload['user_id'])
        if not user_info:
            raise AuthenticationFailed(Constants.user_not_found)

        if token != user_info['access_token']:
            raise AuthenticationFailed(Constants.invalid_access_token)

        try:
            user = User.objects.get(user_id=payload['user_id'])
            local.user_id = user.user_id
        except User.DoesNotExist:
            raise AuthenticationFailed(Constants.user_not_found)

        if not user.is_active:
            raise AuthenticationFailed(Constants.user_not_found)

        request.payload = payload
        return user, payload
