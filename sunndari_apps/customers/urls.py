from django.urls import path
from sunndari_apps.customers.controllers.search_artist import SearchArtistController
from sunndari_apps.customers.controllers.get_artist_detail import ArtistDetailController
from sunndari_apps.customers.controllers.check_availability import CheckAvailabilityController
from sunndari_apps.customers.controllers.create_booking import CreateBookingController
from sunndari_apps.customers.controllers.booking import BookingController
from sunndari_apps.customers.controllers.initiate_payment import InitiatePaymentController
from sunndari_apps.customers.controllers.payment_webhook import PaymentWebhookController
from sunndari_apps.customers.controllers.payment import PaymentController
from sunndari_apps.customers.controllers.review import ReviewController

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

    # Payment
    path('payments/initiate/', InitiatePaymentController.initiate_payment, name='customer_initiate_payment'),
    path('payments/webhook/', PaymentWebhookController.payment_webhook, name='customer_payment_webhook'),
    path('payments/get/', PaymentController.get_payment, name='customer_get_payment'),
    path('payments/get_all/', PaymentController.get_all_payments, name='customer_get_all_payments'),

    # Reviews
    path('reviews/create/', ReviewController.create_review, name='customer_create_review'),
    path('reviews/get/', ReviewController.get_review, name='customer_get_review'),
    path('reviews/get_all/', ReviewController.get_all_reviews, name='customer_get_all_reviews'),
]
