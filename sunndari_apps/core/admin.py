from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.common.admin_columns import preview_column
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus, Brand,
)



@admin.register(ServiceCategory)
class ServiceCategoryAdmin(ModelAdmin):
    list_display = ('category_id', 'name', 'is_active', 'description_preview', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    description_preview = preview_column('Description', 'description')


@admin.register(LocationType)
class LocationTypeAdmin(ModelAdmin):
    list_display = ('location_type_id', 'name', 'is_active', 'description_preview')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    description_preview = preview_column('Description', 'description')


class StatusAdmin(ModelAdmin):
    """Booking, payment and approval statuses: small lookup tables the code relies on by name."""
    list_display = ('status_id', 'name', 'description_preview')
    search_fields = ('name', 'description')
    description_preview = preview_column('Description', 'description')


admin.site.register(BookingStatus, StatusAdmin)
admin.site.register(PaymentStatus, StatusAdmin)
admin.site.register(ApprovalStatus, StatusAdmin)


@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ('brand_id', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(ServiceSubCategory)
class ServiceSubCategoryAdmin(ModelAdmin):
    """The "service" an admin switches on and off. The Active checkbox on the edit page is the control;
    saving it from off to on is what starts the 15-day "new service" window (see ServiceSubCategory.save).
    Turning a service off never touches its parent category, which stays live for its other services."""

    list_display = ('sub_category_id', 'name', 'category', 'is_active', 'activated_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'category__name')
    list_select_related = ('category',)
    # Set by the system, never by hand: shown so an admin can see when the service last went live.
    readonly_fields = ('activated_at', 'activation_notified_at', 'created_at', 'updated_at')
    actions = ('activate_selected', 'deactivate_selected')

    @admin.action(description='Activate selected services', permissions=['change'])
    def activate_selected(self, request, queryset):
        self._set_active(request, queryset, active=True)

    @admin.action(description='Deactivate selected services', permissions=['change'])
    def deactivate_selected(self, request, queryset):
        self._set_active(request, queryset, active=False)

    def _set_active(self, request, queryset, active: bool) -> None:
        """Each service goes through save() — not queryset.update() — so the activation rule runs. Services
        already in the requested state are skipped, which is what keeps a repeated click from restarting
        the 15-day window of a service that is already live."""
        changed = 0
        for service in queryset.exclude(is_active=active):
            service.is_active = active
            service.save()
            changed += 1
        skipped = queryset.count() - changed
        verb = 'activated' if active else 'deactivated'
        message = f'{changed} service(s) {verb}.'
        if skipped:
            message += f' {skipped} already {"active" if active else "inactive"}, left unchanged.'
        self.message_user(request, message)

