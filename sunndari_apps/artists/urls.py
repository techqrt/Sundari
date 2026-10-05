from django.urls import path
from sunndari_apps.artists.controllers.artist_profile import ArtistProfileController
from sunndari_apps.artists.controllers.portfolio import PortfolioController
from sunndari_apps.artists.controllers.pricing_package import PricingPackageController
from sunndari_apps.artists.controllers.availability import AvailabilityController
from sunndari_apps.artists.controllers.booking import ArtistBookingController
from sunndari_apps.artists.controllers.document import ArtistDocumentController
from sunndari_apps.artists.controllers.payout_account import ArtistPayoutAccountController
from sunndari_apps.artists.controllers.onboarding import ArtistOnboardingController
from sunndari_apps.artists.controllers.addon import AddOnController
from sunndari_apps.artists.controllers.reschedule import ArtistRescheduleController
from sunndari_apps.artists.controllers.review import ArtistReviewController
from sunndari_apps.artists.controllers.customer_review import ArtistCustomerReviewController
from sunndari_apps.artists.controllers.client import ArtistClientController
from sunndari_apps.artists.controllers.insights import ArtistInsightsController
from sunndari_apps.artists.controllers.brand_request import ArtistBrandRequestController
from sunndari_apps.artists.controllers.service_area import ServiceAreaController

urlpatterns = [
    # Profile
    path('profile/get/', ArtistProfileController.get_profile, name='artist_get_profile'),
    path('profile/update/', ArtistProfileController.update_profile, name='artist_update_profile'),
    path('profile/agreement/accept/', ArtistProfileController.accept_agreement, name='artist_accept_agreement'),

    # Services
    path('profile/specialities/set/', ArtistProfileController.set_specialities, name='artist_set_specialities'),
    path('profile/specialities/get_all/', ArtistProfileController.get_all_specialities, name='artist_get_all_specialities'),
    path('profile/photo/upload/', ArtistProfileController.upload_photos, name='artist_upload_photos'),
    path('profile/photo/delete/', ArtistProfileController.delete_photo, name='artist_delete_photo'),
    path('profile/accepting_bookings/', ArtistProfileController.set_accepting_bookings, name='artist_set_accepting_bookings'),
    path('profile/share_link/', ArtistProfileController.get_share_link, name='artist_get_share_link'),
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
    path('portfolio/reorder/', PortfolioController.reorder_portfolio, name='artist_reorder_portfolio'),
    path('portfolio/get/', PortfolioController.get_portfolio, name='artist_get_portfolio'),
    path('portfolio/get_all/', PortfolioController.get_all_portfolio, name='artist_get_all_portfolio'),

    # Pricing Packages
    path('packages/create/', PricingPackageController.create_package, name='artist_create_package'),
    path('packages/update/', PricingPackageController.update_package, name='artist_update_package'),
    path('packages/delete/', PricingPackageController.delete_package, name='artist_delete_package'),
    path('packages/get/', PricingPackageController.get_package, name='artist_get_package'),
    path('packages/photo/upload/', PricingPackageController.upload_photo, name='artist_upload_package_photo'),
    path('packages/photo/delete/', PricingPackageController.delete_photo, name='artist_delete_package_photo'),
    path('packages/get_all/', PricingPackageController.get_all_packages, name='artist_get_all_packages'),

    # Availability — Schedule
    path('addons/create/', AddOnController.create_addon, name='artist_create_addon'),
    path('addons/update/', AddOnController.update_addon, name='artist_update_addon'),
    path('addons/delete/', AddOnController.delete_addon, name='artist_delete_addon'),
    path('addons/get/', AddOnController.get_addon, name='artist_get_addon'),
    path('addons/get_all/', AddOnController.get_all_addons, name='artist_get_all_addons'),
    path('service_areas/add/', ServiceAreaController.add_service_area, name='artist_add_service_area'),
    path('service_areas/update/', ServiceAreaController.update_service_area, name='artist_update_service_area'),
    path('service_areas/remove/', ServiceAreaController.remove_service_area, name='artist_remove_service_area'),
    path('service_areas/get_all/', ServiceAreaController.get_all_service_areas, name='artist_get_all_service_areas'),
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
    path('bookings/on_my_way/', ArtistBookingController.on_my_way, name='artist_on_my_way'),
    path('bookings/arrived/', ArtistBookingController.arrived, name='artist_arrived'),
    path('bookings/start_pin/verify/', ArtistBookingController.verify_start_pin, name='artist_verify_start_pin'),
    path('bookings/completion_pin/verify/', ArtistBookingController.verify_completion_pin, name='artist_verify_completion_pin'),

    # Onboarding — Documents
    path('bookings/reschedule/request/', ArtistRescheduleController.request_reschedule, name='artist_request_reschedule'),
    path('bookings/reschedule/cancel/', ArtistRescheduleController.cancel_reschedule, name='artist_cancel_reschedule'),
    path('bookings/reschedule/get_all/', ArtistRescheduleController.get_all_reschedules, name='artist_get_all_reschedules'),
    path('reviews/get_all/', ArtistReviewController.get_all_reviews, name='artist_get_all_reviews'),
    path('reviews/reply/', ArtistReviewController.reply_review, name='artist_reply_review'),
    path('customer_reviews/create/', ArtistCustomerReviewController.create_customer_review, name='artist_create_customer_review'),
    path('customer_reviews/get_all/', ArtistCustomerReviewController.get_all_customer_reviews, name='artist_get_all_customer_reviews'),
    path('clients/get_all/', ArtistClientController.get_all_clients, name='artist_get_all_clients'),
    path('clients/note/set/', ArtistClientController.set_client_note, name='artist_set_client_note'),
    path('insights/summary/', ArtistInsightsController.get_summary, name='artist_insights_summary'),
    path('brands/request/', ArtistBrandRequestController.request_brand, name='artist_request_brand'),
    path('brands/requests/get_all/', ArtistBrandRequestController.get_all_brand_requests, name='artist_get_all_brand_requests'),
    path('documents/create/', ArtistDocumentController.create_document, name='artist_create_document'),
    path('documents/delete/', ArtistDocumentController.delete_document, name='artist_delete_document'),
    path('documents/get/', ArtistDocumentController.get_document, name='artist_get_document'),
    path('documents/file/', ArtistDocumentController.download_document, name='artist_download_document'),
    path('documents/get_all/', ArtistDocumentController.get_all_documents, name='artist_get_all_documents'),

    # Onboarding — Payout Account
    path('payout_account/set/', ArtistPayoutAccountController.set_payout_account, name='artist_set_payout_account'),
    path('payout_account/get/', ArtistPayoutAccountController.get_payout_account, name='artist_get_payout_account'),

    # Onboarding — Status
    path('onboarding/status/', ArtistOnboardingController.get_status, name='artist_onboarding_status'),
    path('review/feedback/get_all/', ArtistOnboardingController.get_feedback, name='artist_review_feedback_get_all'),
    path('onboarding/submit/', ArtistOnboardingController.submit, name='artist_onboarding_submit'),
]
