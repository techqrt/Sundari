from django.urls import path
from sunndari_apps.customers.controllers.search_artist import SearchArtistController
from sunndari_apps.customers.controllers.get_artist_detail import ArtistDetailController
from sunndari_apps.customers.controllers.check_availability import CheckAvailabilityController
from sunndari_apps.customers.controllers.create_booking import CreateBookingController
from sunndari_apps.customers.controllers.booking import BookingController
from sunndari_apps.customers.controllers.review import ReviewController
from sunndari_apps.customers.controllers.service_pin import StartPinController, CompletionPinController

urlpatterns = [
    # Search & Discovery
    path('artists/search/', SearchArtistController.search_artists, name='customer_search_artists'),

    # Artist Profile View
    path('artists/get/', ArtistDetailController.get_artist_detail, name='customer_get_artist_detail'),
    path('artists/availability/', CheckAvailabilityController.check_availability, name='customer_check_artist_availability'),

    # Booking
    path('bookings/create/', CreateBookingController.create_booking, name='customer_create_booking'),
    path('bookings/get/', BookingController.get_booking, name='customer_get_booking'),
    path('bookings/get_all/', BookingController.get_all_bookings, name='customer_get_all_bookings'),
    path('bookings/cancel/', BookingController.cancel_booking, name='customer_cancel_booking'),
    path('bookings/start_pin/', StartPinController.get_start_pin, name='customer_get_start_pin'),
    path('bookings/completion_pin/', CompletionPinController.get_completion_pin, name='customer_get_completion_pin'),

    # Payment — see sunndari_apps.payments.urls, mounted at this same 'customers/payments/'
    # prefix directly in sunndari/urls.py (public API paths unchanged by the app move).

    # Reviews
    path('reviews/create/', ReviewController.create_review, name='customer_create_review'),
    path('reviews/get/', ReviewController.get_review, name='customer_get_review'),
    path('reviews/get_all/', ReviewController.get_all_reviews, name='customer_get_all_reviews'),
]
