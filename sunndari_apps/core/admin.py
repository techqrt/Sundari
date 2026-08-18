from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus,
)

admin.site.register(ServiceCategory, ModelAdmin)
admin.site.register(ServiceSubCategory, ModelAdmin)
admin.site.register(LocationType, ModelAdmin)
admin.site.register(BookingStatus, ModelAdmin)
admin.site.register(PaymentStatus, ModelAdmin)
admin.site.register(ApprovalStatus, ModelAdmin)