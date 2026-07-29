from django.urls import path
from sunndari_apps.authentication.controller import AuthController

urlpatterns = [
    # Phone OTP
    path('phone-otp/request/', AuthController.phone_otp_request, name='phone_otp_request'),
    path('phone-otp/verify/', AuthController.phone_otp_verify, name='phone_otp_verify'),

    # Email OTP
    path('email-otp/request/', AuthController.email_otp_request, name='email_otp_request'),
    path('email-otp/verify/', AuthController.email_otp_verify, name='email_otp_verify'),

    # Password
    path('register/', AuthController.register, name='auth_register'),
    path('login/', AuthController.login, name='auth_login'),

    # Google
    path('google/', AuthController.google_auth, name='google_auth'),

    # Token
    path('token/refresh/', AuthController.token_refresh, name='token_refresh'),
]
