from django.urls import path
from sunndari_apps.artists.controllers.artist_profile import ArtistProfileController
from sunndari_apps.artists.controllers.portfolio import PortfolioController
from sunndari_apps.artists.controllers.pricing_package import PricingPackageController
from sunndari_apps.artists.controllers.availability import AvailabilityController
from sunndari_apps.artists.controllers.booking import ArtistBookingController

urlpatterns = [
    # Profile
    path('profile/get/', ArtistProfileController.get_profile, name='artist_get_profile'),
    path('profile/update/', ArtistProfileController.update_profile, name='artist_update_profile'),

    # Services
    path('services/add/', ArtistProfileController.add_service, name='artist_add_service'),
    path('services/remove/', ArtistProfileController.remove_service, name='artist_remove_service'),
    path('services/get_all/', ArtistProfileController.get_all_services, name='artist_get_all_services'),

    # Location Preferences
    path('locations/add/', ArtistProfileController.add_location, name='artist_add_location'),
    path('locations/remove/', ArtistProfileController.remove_location, name='artist_remove_location'),
    path('locations/get_all/', ArtistProfileController.get_all_locations, name='artist_get_all_locations'),

    # Portfolio
    path('portfolio/create/', PortfolioController.create_portfolio, name='artist_create_portfolio'),
    path('portfolio/update/', PortfolioController.update_portfolio, name='artist_update_portfolio'),
    path('portfolio/delete/', PortfolioController.delete_portfolio, name='artist_delete_portfolio'),
    path('portfolio/get/', PortfolioController.get_portfolio, name='artist_get_portfolio'),
    path('portfolio/get_all/', PortfolioController.get_all_portfolio, name='artist_get_all_portfolio'),

    # Pricing Packages
    path('packages/create/', PricingPackageController.create_package, name='artist_create_package'),
    path('packages/update/', PricingPackageController.update_package, name='artist_update_package'),
    path('packages/delete/', PricingPackageController.delete_package, name='artist_delete_package'),
    path('packages/get/', PricingPackageController.get_package, name='artist_get_package'),
    path('packages/get_all/', PricingPackageController.get_all_packages, name='artist_get_all_packages'),

    # Availability — Schedule
    path('availability/schedule/set/', AvailabilityController.set_schedule, name='artist_set_schedule'),
    path('availability/schedule/remove/', AvailabilityController.remove_schedule, name='artist_remove_schedule'),
    path('availability/schedule/get_all/', AvailabilityController.get_all_schedules, name='artist_get_all_schedules'),

    # Availability — Blocks
    path('availability/block/add/', AvailabilityController.add_block, name='artist_add_block'),
    path('availability/block/remove/', AvailabilityController.remove_block, name='artist_remove_block'),
    path('availability/block/get_all/', AvailabilityController.get_all_blocks, name='artist_get_all_blocks'),

    # Bookings
    path('bookings/get/', ArtistBookingController.get_booking, name='artist_get_booking'),
    path('bookings/get_all/', ArtistBookingController.get_all_bookings, name='artist_get_all_bookings'),
    path('bookings/update_status/', ArtistBookingController.update_booking_status, name='artist_update_booking_status'),
]
