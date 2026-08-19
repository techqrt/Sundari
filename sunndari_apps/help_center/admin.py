from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.help_center.models import SupportConversation, SupportMessage

admin.site.register(SupportConversation, ModelAdmin)
admin.site.register(SupportMessage, ModelAdmin)
