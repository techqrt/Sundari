from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.chat.models import Conversation, Message

admin.site.register(Conversation, ModelAdmin)
admin.site.register(Message, ModelAdmin)
