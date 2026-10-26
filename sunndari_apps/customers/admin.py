from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.common.admin_columns import related_column, preview_column
from sunndari_apps.customers.models import Booking, Review, BookingAddOn, BookingReschedule, CustomerReview

CUSTOMER_SEARCH = ('customer__name', 'customer__phone_number')
ARTIST_SEARCH = ('artist__user__name', 'artist__user__phone_number', 'artist__display_name')


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    # The booking OTP and the start / completion PINs are deliberately not columns.
    list_display = (
        'booking_id', 'customer_name', 'artist_name', 'booking_date', 'start_time', 'status', 'location_type',
        'total_amount', 'cancelled_by', 'created_at',
    )
    list_filter = ('status', 'booking_date', 'location_type', 'cancelled_by')
    search_fields = CUSTOMER_SEARCH + ARTIST_SEARCH
    list_select_related = ('customer', 'artist__user', 'status', 'location_type')
    date_hierarchy = 'booking_date'
    customer_name = related_column('Customer', 'customer__name', 'customer__phone_number')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(BookingAddOn)
class BookingAddOnAdmin(ModelAdmin):
    list_display = ('booking_addon_id', 'booking', 'name', 'price', 'duration_minutes')
    search_fields = ('name', 'booking__customer__name', 'booking__customer__phone_number')
    list_select_related = ('booking',)


@admin.register(BookingReschedule)
class BookingRescheduleAdmin(ModelAdmin):
    list_display = ('reschedule_id', 'booking', 'requested_by_name', 'status', 'previous_date', 'proposed_date', 'proposed_start_time', 'expires_at')
    list_filter = ('status',)
    search_fields = ('requested_by__name', 'requested_by__phone_number')
    list_select_related = ('booking', 'requested_by')
    requested_by_name = related_column('Requested by', 'requested_by__name', 'requested_by__phone_number')


@admin.register(CustomerReview)
class CustomerReviewAdmin(ModelAdmin):
    list_display = ('customer_review_id', 'artist_name', 'customer_name', 'rating', 'comment_preview', 'created_at')
    list_filter = ('rating',)
    search_fields = CUSTOMER_SEARCH + ARTIST_SEARCH + ('comment',)
    list_select_related = ('artist__user', 'customer')
    artist_name = related_column('Artist (rater)', 'artist__user__name', 'artist__user__phone_number')
    customer_name = related_column('Customer (rated)', 'customer__name', 'customer__phone_number')
    comment_preview = preview_column('Comment', 'comment')


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ('review_id', 'customer_name', 'artist_name', 'rating', 'comment_preview', 'has_reply', 'created_at')
    list_filter = ('rating',)
    search_fields = CUSTOMER_SEARCH + ARTIST_SEARCH + ('comment', 'reply')
    list_select_related = ('artist__user', 'customer')
    customer_name = related_column('Customer', 'customer__name', 'customer__phone_number')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')
    comment_preview = preview_column('Comment', 'comment')

    @admin.display(description='Replied', boolean=True, ordering='replied_at')
    def has_reply(self, obj):
        return bool(obj.reply)
