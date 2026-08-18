from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.notifications.models import Notification

admin.site.register(Notification, ModelAdmin)
