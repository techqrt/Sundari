import jwt
from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.conf import settings
from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import get_user_info_from_db


@database_sync_to_async
def _authenticate_token(token: str):
    """Mirrors JWTAuthentication.authenticate — same decode + DB cross-check,
    reused here instead of duplicated, since the WS scope has no DRF request
    to run the existing authentication class against."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.InvalidTokenError:
        return None

    user_info = get_user_info_from_db(user_id=payload['user_id'])
    if not user_info or token != user_info['access_token']:
        return None

    try:
        user = User.objects.get(user_id=payload['user_id'])
    except User.DoesNotExist:
        return None

    if not user.is_active:
        return None
    return user


class JWTAuthWebsocketMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        token = parse_qs(query_string).get('token', [None])[0]
        scope['user'] = await _authenticate_token(token) if token else None
        return await super().__call__(scope, receive, send)
