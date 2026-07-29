from django.contrib import admin
from sunndari_apps.customers.models import Booking, Payment, Review

admin.site.register(Booking)
admin.site.register(Payment)
admin.site.register(Review)
