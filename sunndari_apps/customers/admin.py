from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.customers.models import Booking, Review

admin.site.register(Booking, ModelAdmin)
admin.site.register(Review, ModelAdmin)
