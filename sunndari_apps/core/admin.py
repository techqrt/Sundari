from django import forms
from django.contrib import admin, messages
from django.db import transaction
from unfold.admin import ModelAdmin
from sunndari.constants import Constants
from sunndari_apps.common.admin_columns import preview_column
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus, Brand,
)
from sunndari_apps.core.models.service_sub_category import ANNOUNCEMENT_MESSAGE_MAX



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


class ServiceSubCategoryForm(forms.ModelForm):
    """The edit form, plus two fields that are only instructions for this save and are stored nowhere: whether to tell
    artists about the service now, and the wording to use. Telling artists is always this explicit tick (or the bulk
    action); saving the form without it never notifies anyone."""
    notify_artists = forms.BooleanField(
        required=False, label='Send notification to artists',
        help_text='Tells every approved artist this service is open for them to add. Only works while the service and its category are active.')
    artists_message = forms.CharField(
        required=False, max_length=ANNOUNCEMENT_MESSAGE_MAX, label='Notification message',
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional. Leave blank to send the standard text: "<service> is now available. Add it to your services to start getting bookings."')

    class Meta:
        model = ServiceSubCategory
        fields = ('category', 'name', 'description', 'is_active')

    def clean(self):
        data = super().clean()
        category = data.get('category')
        if data.get('notify_artists') and category is not None and not (data.get('is_active') and category.is_active):
            self.add_error('notify_artists', Constants.service_announce_inactive)
        return data


@admin.register(ServiceSubCategory)
class ServiceSubCategoryAdmin(ModelAdmin):
    """The "service" an admin switches on and off. The Active checkbox on the edit page is the control;
    saving it from off to on is what starts the 15-day "new service" window (see ServiceSubCategory.save).
    Turning a service off never touches its parent category, which stays live for its other services.
    Activating or deactivating never notifies artists: that is the separate "Send notification to artists" tick
    or the "Announce selected services to artists" action, each recorded in the admin history."""

    form = ServiceSubCategoryForm

    list_display = ('sub_category_id', 'name', 'category', 'is_active', 'activated_at', 'artists_announced_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'category__name')
    list_select_related = ('category',)
    # Set by the system, never by hand: shown so an admin can see when the service last went live.
    readonly_fields = ('activated_at', 'artists_announced_at', 'artists_notified_at', 'artists_announcement_message',
                       'created_at', 'updated_at')
    fields = ('category', 'name', 'description', 'is_active', 'notify_artists', 'artists_message', 'activated_at',
              'artists_announced_at', 'artists_notified_at', 'artists_announcement_message', 'created_at', 'updated_at')
    actions = ('activate_selected', 'deactivate_selected', 'announce_selected')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get('notify_artists'):
            self._announce(request, obj, form.cleaned_data.get('artists_message'))

    def _announce(self, request, service, message=None) -> bool:
        """Records the announcement, writes it to the admin history, and queues the job once the surrounding save is
        committed. A broker that is down does not undo the announcement; the periodic job sends it. Returns whether the
        announcement was recorded."""
        try:
            announced_at = ServiceSubCategory.announce_to_artists(service.pk, message)
        except ValueError as error:
            self.message_user(request, f'{service.name}: {error}', level=messages.ERROR)
            return False
        self.log_change(request, service, f'Announced to artists: "{ServiceSubCategory.objects.get(pk=service.pk).artists_announcement_message}"')
        sub_category_id = service.pk

        def queue():
            if not ServiceSubCategory.dispatch_artist_announcement(sub_category_id, announced_at):
                self.message_user(request, f'{service.name}: the queue is unavailable, the notification will go out shortly.',
                                  level=messages.WARNING)
        transaction.on_commit(queue)
        self.message_user(request, f'{service.name}: artists are being notified.')
        return True

    @admin.action(description='Announce selected services to artists', permissions=['change'])
    def announce_selected(self, request, queryset):
        """Sends each selected live service to artists with the standard wording; services that are switched off are
        refused (reported by name) and the rest still go out."""
        for service in queryset.select_related('category'):
            self._announce(request, service)

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

