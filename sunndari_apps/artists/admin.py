from django.contrib import admin
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistServiceOffering, ArtistLocationPreference,
    Portfolio, PricingPackage, PackageInclusion,
    ArtistAvailabilitySchedule, ArtistAvailabilityBlock,
)

admin.site.register(ArtistProfile)
admin.site.register(ArtistServiceOffering)
admin.site.register(ArtistLocationPreference)
admin.site.register(Portfolio)
admin.site.register(PricingPackage)
admin.site.register(PackageInclusion)
admin.site.register(ArtistAvailabilitySchedule)
admin.site.register(ArtistAvailabilityBlock)