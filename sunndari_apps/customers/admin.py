from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.customers.models import Booking, Payment, Review

admin.site.register(Booking, ModelAdmin)
admin.site.register(Payment, ModelAdmin)
admin.site.register(Review, ModelAdmin)
