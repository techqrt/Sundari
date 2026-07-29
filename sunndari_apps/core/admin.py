from django.contrib import admin
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus,
)

admin.site.register(ServiceCategory)
admin.site.register(ServiceSubCategory)
admin.site.register(LocationType)
admin.site.register(BookingStatus)
admin.site.register(PaymentStatus)
admin.site.register(ApprovalStatus)