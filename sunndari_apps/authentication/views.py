from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import (
    generate_jwt_token,
    generate_refresh_token,
    send_otp_sms,
    send_otp_email,
    verify_google_token,
)
from sunndari_apps.authentication.serializers_auth import (
    PhoneOTPRequestSerializer,
    PhoneOTPVerifySerializer,
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    RegisterWithPasswordSerializer,
    LoginWithPasswordSerializer,
    GoogleAuthSerializer,
    TokenRefreshSerializer,
)
from sunndari_apps.common.utils import Utils
from sunndari.constants import Constants


def _create_role_instance(user: User) -> None:
    if user.role == 'artist':
        from sunndari_apps.artists.models.artist_profile import ArtistProfile
        if not ArtistProfile.objects.filter(user_id=user.user_id).exists():
            ArtistProfile.create_for_user(user_id=user.user_id)


def _issue_token(user: User) -> Response:
    access_token = generate_jwt_token(user)
    refresh_token = generate_refresh_token(user)
    user.access_token = access_token
    user.refresh_token = refresh_token
    user.save()
    return Response(
        status=status.HTTP_200_OK,
        data=Utils.success_response_data(
            message=Constants.auth_success,
            data={
                'user_id': user.user_id,
                'name': user.name,
                'email': user.email,
                'phone_number': user.phone_number,
                'role': user.role,
                'access_token': access_token,
                'refresh_token': refresh_token,
            }
        )
    )


class PhoneOTPView:
    def request_otp(self, params: dict) -> Response:
        serializer = PhoneOTPRequestSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        phone_number = serializer.validated_data['phone_number']
        role = serializer.validated_data.get('role')

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            if not role:
                return Response(
                    Utils.error_response_data(Constants.user_not_found, [Constants.user_not_found]),
                    status=status.HTTP_404_NOT_FOUND
                )
            with transaction.atomic():
                user = User.objects.create(phone_number=phone_number, role=role)
                _create_role_instance(user)

        if user.is_locked_out():
            return Response(
                Utils.error_response_data(Constants.account_locked, [Constants.account_locked]),
                status=status.HTTP_403_FORBIDDEN
            )

        otp = user.generate_otp()
        send_otp_sms(phone_number, otp)

        return Response(
            Utils.success_response_data(message=Constants.otp_sent),
            status=status.HTTP_200_OK
        )

    def verify_otp(self, params: dict) -> Response:
        serializer = PhoneOTPVerifySerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        phone_number = serializer.validated_data['phone_number']
        otp = int(serializer.validated_data['otp'])

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return Response(
                Utils.error_response_data(Constants.user_not_found, [Constants.user_not_found]),
                status=status.HTTP_404_NOT_FOUND
            )

        if user.is_locked_out():
            return Response(
                Utils.error_response_data(Constants.account_locked, [Constants.account_locked]),
                status=status.HTTP_403_FORBIDDEN
            )

        if user.otp != otp or not user.otp_expiry or timezone.now() > user.otp_expiry:
            user.increment_otp_attempts()
            return Response(
                Utils.error_response_data(Constants.otp_invalid, [Constants.otp_invalid]),
                status=status.HTTP_400_BAD_REQUEST
            )

        user.otp = None
        user.otp_expiry = None
        user.otp_attempts = 0
        user.save()

        return _issue_token(user)


class EmailOTPView:
    def request_otp(self, params: dict) -> Response:
        serializer = EmailOTPRequestSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']
        role = serializer.validated_data.get('role')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            if not role:
                return Response(
                    Utils.error_response_data(Constants.user_not_found, [Constants.user_not_found]),
                    status=status.HTTP_404_NOT_FOUND
                )
            with transaction.atomic():
                user = User.objects.create(email=email, role=role)
                _create_role_instance(user)

        if user.is_locked_out():
            return Response(
                Utils.error_response_data(Constants.account_locked, [Constants.account_locked]),
                status=status.HTTP_403_FORBIDDEN
            )

        otp = user.generate_otp()
        send_otp_email(email, otp)

        return Response(
            Utils.success_response_data(message=Constants.otp_sent),
            status=status.HTTP_200_OK
        )

    def verify_otp(self, params: dict) -> Response:
        serializer = EmailOTPVerifySerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']
        otp = int(serializer.validated_data['otp'])

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                Utils.error_response_data(Constants.user_not_found, [Constants.user_not_found]),
                status=status.HTTP_404_NOT_FOUND
            )

        if user.is_locked_out():
            return Response(
                Utils.error_response_data(Constants.account_locked, [Constants.account_locked]),
                status=status.HTTP_403_FORBIDDEN
            )

        if user.otp != otp or not user.otp_expiry or timezone.now() > user.otp_expiry:
            user.increment_otp_attempts()
            return Response(
                Utils.error_response_data(Constants.otp_invalid, [Constants.otp_invalid]),
                status=status.HTTP_400_BAD_REQUEST
            )

        user.otp = None
        user.otp_expiry = None
        user.otp_attempts = 0
        user.save()

        return _issue_token(user)


class PasswordAuthView:
    def register(self, params: dict) -> Response:
        serializer = RegisterWithPasswordSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        email = data.get('email')
        phone_number = data.get('phone_number')

        if email and User.objects.filter(email=email).exists():
            return Response(
                Utils.error_response_data(Constants.email_not_unique, [Constants.email_not_unique]),
                status=status.HTTP_400_BAD_REQUEST
            )
        if phone_number and User.objects.filter(phone_number=phone_number).exists():
            return Response(
                Utils.error_response_data(Constants.mobile_number_not_unique, [Constants.mobile_number_not_unique]),
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            user = User.objects.create(
                name=data['name'],
                email=email,
                phone_number=phone_number,
                role=data['role'],
            )
            user.set_password(data['password'])
            user.save()
            _create_role_instance(user)

        return _issue_token(user)

    def login(self, params: dict) -> Response:
        serializer = LoginWithPasswordSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        try:
            user = (
                User.objects.get(email=username)
                if '@' in username
                else User.objects.get(phone_number=username)
            )
        except User.DoesNotExist:
            return Response(
                Utils.error_response_data(Constants.auth_error, [Constants.auth_error]),
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.check_password(password):
            return Response(
                Utils.error_response_data(Constants.auth_error, [Constants.auth_error]),
                status=status.HTTP_401_UNAUTHORIZED
            )

        return _issue_token(user)


class GoogleAuthView:
    def authenticate(self, params: dict) -> Response:
        serializer = GoogleAuthSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            google_data = verify_google_token(serializer.validated_data['id_token'])
        except Exception:
            return Response(
                Utils.error_response_data(Constants.auth_error, ['Invalid Google token']),
                status=status.HTTP_401_UNAUTHORIZED
            )

        google_id = google_data['google_id']
        email = google_data.get('email')
        name = google_data.get('name', '')
        role = serializer.validated_data.get('role')

        user = User.objects.filter(google_id=google_id).first()

        if not user and email:
            user = User.objects.filter(email=email).first()

        if not user:
            if not role:
                return Response(
                    Utils.error_response_data(Constants.user_not_found, ['Role is required for first-time Google login']),
                    status=status.HTTP_400_BAD_REQUEST
                )
            with transaction.atomic():
                user = User.objects.create(
                    name=name,
                    email=email,
                    google_id=google_id,
                    role=role,
                )
                _create_role_instance(user)
        else:
            if not user.google_id:
                user.google_id = google_id
                user.save()

        return _issue_token(user)


class TokenRefreshView:
    def refresh(self, params: dict) -> Response:
        import jwt as pyjwt
        from django.conf import settings

        serializer = TokenRefreshSerializer(data=params)
        if not serializer.is_valid():
            return Response(
                Utils.error_response_data(Constants.validation_error, [serializer.errors]),
                status=status.HTTP_400_BAD_REQUEST
            )

        refresh_token = serializer.validated_data['refresh_token']

        try:
            payload = pyjwt.decode(refresh_token, settings.SECRET_KEY, algorithms=['HS256'])
        except pyjwt.ExpiredSignatureError:
            return Response(
                Utils.error_response_data(Constants.refresh_token_invalid, [Constants.refresh_token_invalid]),
                status=status.HTTP_401_UNAUTHORIZED
            )
        except pyjwt.InvalidTokenError:
            return Response(
                Utils.error_response_data(Constants.refresh_token_invalid, [Constants.refresh_token_invalid]),
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            user = User.objects.get(user_id=payload['user_id'])
        except User.DoesNotExist:
            return Response(
                Utils.error_response_data(Constants.user_not_found, [Constants.user_not_found]),
                status=status.HTTP_404_NOT_FOUND
            )

        if user.refresh_token != refresh_token:
            return Response(
                Utils.error_response_data(Constants.refresh_token_invalid, [Constants.refresh_token_invalid]),
                status=status.HTTP_401_UNAUTHORIZED
            )

        return _issue_token(user)
