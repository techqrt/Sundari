from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistServiceOffering, ArtistLocationPreference,
    Portfolio, PricingPackage, PackageInclusion,
    ArtistAvailabilitySchedule, ArtistAvailabilityBlock,
    ArtistDocument, ArtistPayoutAccount, ArtistSpeciality, ArtistReviewFeedback,
    PackageAddOn, ArtistServiceArea, ArtistClientNote, BrandRequest,
)


@admin.register(ArtistProfile)
class ArtistProfileAdmin(ModelAdmin):
    list_display = ('artist_id', 'artist_name', 'phone_number')

    @admin.display(description='Name', ordering='user__name')
    def artist_name(self, obj):
        return obj.user.name

    @admin.display(description='Phone number', ordering='user__phone_number')
    def phone_number(self, obj):
        return obj.user.phone_number


admin.site.register(ArtistServiceOffering, ModelAdmin)
admin.site.register(ArtistLocationPreference, ModelAdmin)
admin.site.register(Portfolio, ModelAdmin)
admin.site.register(PricingPackage, ModelAdmin)
admin.site.register(PackageInclusion, ModelAdmin)
admin.site.register(ArtistAvailabilitySchedule, ModelAdmin)
admin.site.register(ArtistAvailabilityBlock, ModelAdmin)
admin.site.register(ArtistDocument, ModelAdmin)
admin.site.register(ArtistPayoutAccount, ModelAdmin)
admin.site.register(ArtistSpeciality, ModelAdmin)
admin.site.register(ArtistReviewFeedback, ModelAdmin)
admin.site.register(PackageAddOn, ModelAdmin)
admin.site.register(ArtistServiceArea, ModelAdmin)
admin.site.register(ArtistClientNote, ModelAdmin)
admin.site.register(BrandRequest, ModelAdmin)
