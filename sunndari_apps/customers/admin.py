from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.customers.models import Booking, Review, BookingAddOn, BookingReschedule, CustomerReview

admin.site.register(Booking, ModelAdmin)
admin.site.register(Review, ModelAdmin)
admin.site.register(BookingAddOn, ModelAdmin)
admin.site.register(BookingReschedule, ModelAdmin)
admin.site.register(CustomerReview, ModelAdmin)
