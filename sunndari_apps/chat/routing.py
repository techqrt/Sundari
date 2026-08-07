from django.urls import re_path
from sunndari_apps.chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r'^ws/chat/(?P<booking_id>\d+)/$', ChatConsumer.as_asgi()),
]
