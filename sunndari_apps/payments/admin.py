from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.payments.models import Payment

admin.site.register(Payment, ModelAdmin)
