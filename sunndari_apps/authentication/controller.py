from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.authentication.serializers_auth import (
    PhoneOTPRequestSerializer,
    PhoneOTPVerifySerializer,
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    RegisterWithPasswordSerializer,
    LoginWithPasswordSerializer,
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
