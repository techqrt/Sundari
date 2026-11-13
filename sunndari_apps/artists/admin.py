from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistServiceOffering, ArtistLocationPreference,
    Portfolio, PricingPackage, PackageInclusion,
    ArtistAvailabilitySchedule, ArtistAvailabilityBlock,
    ArtistDocument, ArtistPayoutAccount, ArtistSpeciality, ArtistReviewFeedback,
    PackageAddOn, ArtistServiceArea, ArtistSalonAddress, ArtistClientNote, BrandRequest,
    PromoCode, PromoRedemption, ArtistRegistrationPayment,
)
from sunndari_apps.common.admin_columns import related_column, preview_column

ARTIST_SEARCH = ('artist__user__name', 'artist__user__phone_number', 'artist__display_name')


@admin.register(ArtistProfile)
class ArtistProfileAdmin(ModelAdmin):
    list_display = (
        'artist_id', 'artist_name', 'phone_number', 'city', 'approval_status', 'portfolio_approval_status',
        'is_accepting_bookings', 'avg_rating', 'created_at',
    )
    list_filter = (
        'approval_status', 'portfolio_approval_status', 'is_accepting_bookings', 'profile_type', 'registration_fee_exempt',
    )
    search_fields = ('user__name', 'user__phone_number', 'user__email', 'display_name', 'city')
    list_select_related = ('user', 'approval_status')
    # The bookings switch and the admin lock are changed only through the rules that guard them (the artist's own
    # switch, and the admin panel's, which needs approval and a settled fee to switch on). Left editable here, one
    # tick could store ON for an unpaid artist, who would then go live by themselves the moment they pay, or clear an
    # admin's switch-off. They are still shown, just not editable. The fee waiver (registration_fee_exempt) stays
    # editable: it is the admin's deliberate way to waive the fee.
    readonly_fields = ('is_accepting_bookings', 'accepting_locked_by_admin')

    @admin.display(description='Name', ordering='user__name')
    def artist_name(self, obj):
        return obj.user.name

    @admin.display(description='Phone number', ordering='user__phone_number')
    def phone_number(self, obj):
        return obj.user.phone_number


@admin.register(ArtistAvailabilityBlock)
class ArtistAvailabilityBlockAdmin(ModelAdmin):
    list_display = ('block_id', 'artist_name', 'block_date', 'start_time', 'end_time', 'note')
    list_filter = ('block_date',)
    search_fields = ARTIST_SEARCH + ('note',)
    list_select_related = ('artist__user',)
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistAvailabilitySchedule)
class ArtistAvailabilityScheduleAdmin(ModelAdmin):
    list_display = ('schedule_id', 'artist_name', 'day_of_week', 'start_time', 'end_time', 'location_type', 'is_active')
    list_filter = ('day_of_week', 'is_active', 'location_type')
    search_fields = ARTIST_SEARCH
    list_select_related = ('artist__user', 'location_type')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistClientNote)
class ArtistClientNoteAdmin(ModelAdmin):
    list_display = ('note_id', 'artist_name', 'customer_name', 'note_preview', 'updated_at')
    search_fields = ARTIST_SEARCH + ('customer__name', 'customer__phone_number', 'note')
    list_select_related = ('artist__user', 'customer')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')
    customer_name = related_column('Customer', 'customer__name', 'customer__phone_number')
    note_preview = preview_column('Note', 'note')


@admin.register(ArtistDocument)
class ArtistDocumentAdmin(ModelAdmin):
    # The ID number and the file are deliberately not columns: they are personal data, shown only on the edit page.
    list_display = ('document_id', 'artist_name', 'document_type', 'id_type', 'verification_status', 'created_at')
    list_filter = ('verification_status', 'document_type', 'id_type')
    search_fields = ARTIST_SEARCH
    list_select_related = ('artist__user', 'verification_status')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistLocationPreference)
class ArtistLocationPreferenceAdmin(ModelAdmin):
    list_display = ('preference_id', 'artist_name', 'location_type')
    list_filter = ('location_type',)
    search_fields = ARTIST_SEARCH
    list_select_related = ('artist__user', 'location_type')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistPayoutAccount)
class ArtistPayoutAccountAdmin(ModelAdmin):
    # Account number, IFSC and UPI id are deliberately not columns.
    list_display = ('payout_account_id', 'artist_name', 'account_holder_name', 'verification_status', 'updated_at')
    list_filter = ('verification_status',)
    search_fields = ARTIST_SEARCH + ('account_holder_name',)
    list_select_related = ('artist__user', 'verification_status')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistReviewFeedback)
class ArtistReviewFeedbackAdmin(ModelAdmin):
    list_display = ('feedback_id', 'artist_name', 'decision', 'reviewed_by', 'message_preview', 'created_at')
    list_filter = ('decision',)
    search_fields = ARTIST_SEARCH + ('message',)
    list_select_related = ('artist__user', 'admin_user')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')
    reviewed_by = related_column('Reviewed by', 'admin_user__name', 'admin_user__phone_number', ordering='admin_user__name')
    message_preview = preview_column('Message', 'message')


@admin.register(ArtistServiceArea)
class ArtistServiceAreaAdmin(ModelAdmin):
    list_display = ('area_id', 'artist_name', 'city', 'travel_charge_type', 'charge_amount', 'is_active')
    list_filter = ('travel_charge_type', 'is_active')
    search_fields = ARTIST_SEARCH + ('city',)
    list_select_related = ('artist__user',)
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistSalonAddress)
class ArtistSalonAddressAdmin(ModelAdmin):
    list_display = ('salon_address_id', 'artist_name', 'name', 'city', 'pin_code', 'latitude', 'longitude', 'is_active')
    list_filter = ('is_active',)
    search_fields = ARTIST_SEARCH + ('name', 'city', 'pin_code')
    list_select_related = ('artist__user',)
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistServiceOffering)
class ArtistServiceOfferingAdmin(ModelAdmin):
    list_display = ('offering_id', 'artist_name', 'sub_category', 'custom_price', 'custom_duration_minutes', 'is_active')
    list_filter = ('is_active', 'sub_category__category')
    search_fields = ARTIST_SEARCH + ('sub_category__name',)
    list_select_related = ('artist__user', 'sub_category__category')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistSpeciality)
class ArtistSpecialityAdmin(ModelAdmin):
    list_display = ('speciality_id', 'artist_name', 'sub_category', 'created_at')
    list_filter = ('sub_category__category',)
    search_fields = ARTIST_SEARCH + ('sub_category__name',)
    list_select_related = ('artist__user', 'sub_category__category')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(BrandRequest)
class BrandRequestAdmin(ModelAdmin):
    list_display = ('request_id', 'artist_name', 'name', 'status', 'decided_at', 'created_at')
    list_filter = ('status',)
    search_fields = ARTIST_SEARCH + ('name',)
    list_select_related = ('artist__user',)
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(PackageAddOn)
class PackageAddOnAdmin(ModelAdmin):
    list_display = ('addon_id', 'name', 'artist_name', 'price', 'duration_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ARTIST_SEARCH + ('name',)
    list_select_related = ('artist__user',)
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(PackageInclusion)
class PackageInclusionAdmin(ModelAdmin):
    list_display = ('inclusion_id', 'package', 'artist_name', 'inclusion_preview', 'order')
    search_fields = ('inclusion_text', 'package__name') + tuple('package__' + f for f in ARTIST_SEARCH)
    list_select_related = ('package__artist__user',)
    artist_name = related_column('Artist', 'package__artist__user__name', 'package__artist__user__phone_number')
    inclusion_preview = preview_column('Inclusion', 'inclusion_text')


@admin.register(Portfolio)
class PortfolioAdmin(ModelAdmin):
    list_display = (
        'portfolio_id', 'artist_name', 'media_type', 'sub_category', 'approval_status', 'is_work_sample', 'is_active', 'created_at',
    )
    list_filter = ('media_type', 'approval_status', 'is_work_sample', 'is_active')
    search_fields = ARTIST_SEARCH + ('caption', 'sub_category__name')
    list_select_related = ('artist__user', 'sub_category', 'approval_status')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(PricingPackage)
class PricingPackageAdmin(ModelAdmin):
    list_display = ('package_id', 'name', 'artist_name', 'sub_category', 'price', 'duration_minutes', 'is_active')
    list_filter = ('is_active', 'sub_category__category')
    search_fields = ARTIST_SEARCH + ('name', 'sub_category__name')
    list_select_related = ('artist__user', 'sub_category__category')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(PromoCode)
class PromoCodeAdmin(ModelAdmin):
    list_display = ('promo_id', 'code', 'discount_percent', 'is_active', 'valid_from', 'valid_until', 'max_redemptions', 'used')
    list_filter = ('is_active',)
    search_fields = ('code',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Used')
    def used(self, obj):
        return obj.redemptions.filter(status__in=['reserved', 'redeemed']).count()


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(ModelAdmin):
    list_display = ('redemption_id', 'promo', 'artist_name', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('promo__code',) + ARTIST_SEARCH
    list_select_related = ('promo', 'artist__user')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')


@admin.register(ArtistRegistrationPayment)
class ArtistRegistrationPaymentAdmin(ModelAdmin):
    list_display = (
        'registration_payment_id', 'artist_name', 'fee_amount', 'discount_percent', 'payable_amount',
        'promo', 'status', 'gateway', 'paid_at', 'created_at',
    )
    list_filter = ('status', 'gateway')
    search_fields = ARTIST_SEARCH + ('gateway_order_id', 'gateway_payment_id', 'promo__code')
    list_select_related = ('artist__user', 'promo', 'status')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')
