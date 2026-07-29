from django.urls import path
from sunndari_apps.core.controllers.service_category import ServiceCategoryController
from sunndari_apps.core.controllers.service_sub_category import ServiceSubCategoryController
from sunndari_apps.core.controllers.location_type import LocationTypeController
from sunndari_apps.core.controllers.statuses import StatusesController

urlpatterns = [
    # Service Category
    path('service-category/get/', ServiceCategoryController.get_service_category, name='get_service_category'),
    path('service-category/get_all/', ServiceCategoryController.get_all_service_categories, name='get_all_service_categories'),

    # Service Sub-Category
    path('service-sub-category/get/', ServiceSubCategoryController.get_service_sub_category, name='get_service_sub_category'),
    path('service-sub-category/get_all/', ServiceSubCategoryController.get_all_service_sub_categories, name='get_all_service_sub_categories'),

    # Location Type
    path('location-type/get/', LocationTypeController.get_location_type, name='get_location_type'),
    path('location-type/get_all/', LocationTypeController.get_all_location_types, name='get_all_location_types'),

    # Statuses
    path('booking-status/get_all/', StatusesController.get_booking_statuses, name='get_booking_statuses'),
    path('payment-status/get_all/', StatusesController.get_payment_statuses, name='get_payment_statuses'),
    path('approval-status/get_all/', StatusesController.get_approval_statuses, name='get_approval_statuses'),
]
