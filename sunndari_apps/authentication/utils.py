import jwt
import datetime
from django.conf import settings
from django.core.mail import send_mail
from sunndari_apps.authentication.models import User


def generate_jwt_token(user: User) -> str:
    payload = {
        'user_id': user.user_id,
        'role': user.role,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
        'iat': datetime.datetime.now(datetime.timezone.utc),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token


def generate_refresh_token(user: User) -> str:
    payload = {
        'user_id': user.user_id,
        'role': user.role,
        'type': 'refresh',
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
        'iat': datetime.datetime.now(datetime.timezone.utc),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token


def get_user_info_from_db(user_id: int) -> dict:
    return User.get(user_id=user_id)


def send_otp_sms(phone_number: str, otp: int) -> None:
    # TODO: integrate SMS gateway (Twilio / MSG91)
    print(f"[SMS] OTP {otp} sent to {phone_number}")


def send_otp_email(email: str, otp: int) -> None:
    send_mail(
        subject='Your SUNNDARI OTP',
        message=f'Your OTP is {otp}. It is valid for 10 minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def verify_google_token(id_token: str) -> dict:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    idinfo = google_id_token.verify_oauth2_token(
        id_token,
        google_requests.Request(),
        settings.GOOGLE_CLIENT_ID,
    )
    return {
        'google_id': idinfo['sub'],
        'email': idinfo.get('email'),
        'name': idinfo.get('name', ''),
    }
