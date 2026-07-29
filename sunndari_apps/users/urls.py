from django.urls import path
from sunndari_apps.users.controllers.customer_address import CustomerAddressController
from sunndari_apps.users.controllers.user_profile import UserProfileController

urlpatterns = [
    # Profile
    path('profile/get/', UserProfileController.get_profile, name='get_profile'),
    path('profile/update/', UserProfileController.update_profile, name='update_profile'),

    # Address
    path('address/create/', CustomerAddressController.create_address, name='create_address'),
    path('address/update/', CustomerAddressController.update_address, name='update_address'),
    path('address/delete/', CustomerAddressController.delete_address, name='delete_address'),
    path('address/get/', CustomerAddressController.get_address, name='get_address'),
    path('address/get_all/', CustomerAddressController.get_all_address, name='get_all_address'),
]
