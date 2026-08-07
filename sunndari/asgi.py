import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sunndari.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from sunndari_apps.chat.middleware import JWTAuthWebsocketMiddleware  # noqa: E402
from sunndari_apps.chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': JWTAuthWebsocketMiddleware(URLRouter(websocket_urlpatterns)),
})
