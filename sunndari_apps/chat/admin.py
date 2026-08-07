from django.contrib import admin
from sunndari_apps.chat.models import Conversation, Message

admin.site.register(Conversation)
admin.site.register(Message)
