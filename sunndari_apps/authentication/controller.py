from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.authentication.serializers_auth import (
    PhoneOTPRequestSerializer,
    PhoneOTPVerifySerializer,
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    RegisterWithPasswordSerializer,
    LoginWithPasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    SetPasswordSerializer,
    GoogleAuthSerializer,
    TokenRefreshSerializer,
    AuthResponseSerializer,
)
from sunndari_apps.authentication.views import (
    PhoneOTPView,
    EmailOTPView,
    PasswordAuthView,
    GoogleAuthView,
    TokenRefreshView,
)
from sunndari_apps.common.swagger import SwaggerPage


class AuthController:

    # ─── Phone OTP ────────────────────────────────────────────────────────────

    @extend_schema(
        description='Request OTP via phone number. Creates user if role is provided and user does not exist.',
        request=PhoneOTPRequestSerializer,
        responses=SwaggerPage.response(description='OTP sent to phone'),
        tags=['Authentication - Phone OTP'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def phone_otp_request(request: Request) -> Response:
        return PhoneOTPView().request_otp(params=request.data)

    @extend_schema(
        description='Verify phone OTP and receive JWT access token.',
        request=PhoneOTPVerifySerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='JWT issued'),
        tags=['Authentication - Phone OTP'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def phone_otp_verify(request: Request) -> Response:
        return PhoneOTPView().verify_otp(params=request.data)

    # ─── Email OTP ────────────────────────────────────────────────────────────

    @extend_schema(
        description='Request OTP via email. Creates user if role is provided and user does not exist.',
        request=EmailOTPRequestSerializer,
        responses=SwaggerPage.response(description='OTP sent to email'),
        tags=['Authentication - Email OTP'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def email_otp_request(request: Request) -> Response:
        return EmailOTPView().request_otp(params=request.data)

    @extend_schema(
        description='Verify email OTP and receive JWT access token.',
        request=EmailOTPVerifySerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='JWT issued'),
        tags=['Authentication - Email OTP'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def email_otp_verify(request: Request) -> Response:
        return EmailOTPView().verify_otp(params=request.data)

    # ─── Password ─────────────────────────────────────────────────────────────

    @extend_schema(
        description='Register a new user with name, email/phone, password and role.',
        request=RegisterWithPasswordSerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='User registered and JWT issued'),
        tags=['Authentication - Password'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def register(request: Request) -> Response:
        return PasswordAuthView().register(params=request.data)

    @extend_schema(
        description='Login with email or phone number and password.',
        request=LoginWithPasswordSerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='JWT issued'),
        tags=['Authentication - Password'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def login(request: Request) -> Response:
        return PasswordAuthView().login(params=request.data)

    @extend_schema(
        description='Request a password-reset OTP (sent by email or SMS). Always responds 200 so registered accounts are not revealed.',
        request=ForgotPasswordSerializer,
        responses=SwaggerPage.response(description='If the account exists, an OTP was sent'),
        tags=['Authentication - Password'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def forgot_password(request: Request) -> Response:
        return PasswordAuthView().forgot_password(params=request.data)

    @extend_schema(
        description='Reset the password using the OTP from forgot-password. Revokes existing sessions; log in again afterwards.',
        request=ResetPasswordSerializer,
        responses=SwaggerPage.response(description='Password reset successfully'),
        tags=['Authentication - Password'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def reset_password(request: Request) -> Response:
        return PasswordAuthView().reset_password(params=request.data)

    @extend_schema(
        description='Set a first password for the logged-in account (phone OTP / Google sign-ups have none). Refused with 400 if a password already exists; use forgot-password to change it. The current session stays valid.',
        request=SetPasswordSerializer,
        responses=SwaggerPage.response(description='Password set successfully'),
        tags=['Authentication - Password'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    def set_password(request: Request) -> Response:
        return PasswordAuthView().set_password(user=request.user, params=request.data)

    # ─── Google ───────────────────────────────────────────────────────────────

    @extend_schema(
        description='Authenticate with a Google ID token. Creates user on first login.',
        request=GoogleAuthSerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='JWT issued'),
        tags=['Authentication - Google'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def google_auth(request: Request) -> Response:
        return GoogleAuthView().authenticate(params=request.data)

    # ─── Token Refresh ────────────────────────────────────────────────────────

    @extend_schema(
        description='Refresh JWT using a valid refresh token.',
        request=TokenRefreshSerializer,
        responses=SwaggerPage.response(response=AuthResponseSerializer, description='New JWT issued'),
        tags=['Authentication'],
    )
    @csrf_exempt
    @api_view(['POST'])
    @permission_classes([AllowAny])
    def token_refresh(request: Request) -> Response:
        return TokenRefreshView().refresh(params=request.data)
