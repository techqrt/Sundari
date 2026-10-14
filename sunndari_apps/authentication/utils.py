import json
import logging
import jwt
import datetime
import requests
from django.conf import settings
from django.core.mail import send_mail
from sunndari_apps.authentication.models import User
from sunndari.config import Configurations


logger = logging.getLogger(__name__)


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


class SMSDeliveryError(Exception):
    """The SMS gateway did not accept the message (or could not be reached/understood).
    Carries no credentials, URL or OTP: the underlying exception is deliberately dropped because
    requests puts the full credential-bearing URL in its error text."""


def _submit_to_gateway(phone_number: str, otp: int) -> None:
    c = Configurations
    required = (c.sms_gateway_url, c.sms_gateway_user, c.sms_gateway_password,
                c.sms_gateway_sender_id, c.sms_gateway_route)
    if not all(required):
        logger.error('SMS gateway is not configured (SMS_GATEWAY_* environment variables)')
        raise SMSDeliveryError()
    # The gateway's sample uses the 10-digit national number, so a +91/91 or trunk-0 prefix is dropped.
    number = ''.join(ch for ch in phone_number if ch.isdigit())
    if len(number) == 12 and number.startswith('91'):
        number = number[2:]
    elif len(number) == 11 and number.startswith('0'):
        number = number[1:]
    params = {
        'user': c.sms_gateway_user,
        'password': c.sms_gateway_password,
        'senderid': c.sms_gateway_sender_id,
        'channel': c.sms_gateway_channel,
        'DCS': c.sms_gateway_dcs,
        'flashsms': c.sms_gateway_flashsms,
        'number': number,
        'text': c.sms_otp_template.format(otp=otp, expiry_minutes=c.otp_expiry_minutes),
        'route': c.sms_gateway_route,
    }
    try:
        response = requests.get(
            c.sms_gateway_url, params=params,
            timeout=(c.sms_gateway_connect_timeout_seconds, c.sms_gateway_read_timeout_seconds),
        )
    except requests.RequestException as exc:
        # Only the exception class is logged: str(exc) contains the URL, password included.
        logger.warning('SMS gateway request failed: %s', type(exc).__name__)
        raise SMSDeliveryError() from None
    if not response.ok:
        logger.warning('SMS gateway returned HTTP %s', response.status_code)
        raise SMSDeliveryError()
    try:
        body = json.loads(response.text)
        error_code = str(body['ErrorCode'])
    except (ValueError, KeyError, TypeError):
        logger.warning('SMS gateway returned an unreadable response')
        raise SMSDeliveryError() from None
    if error_code != c.sms_gateway_success_code:
        logger.warning('SMS gateway rejected the message (ErrorCode %s)', error_code[:10])
        raise SMSDeliveryError()


def send_otp_sms(phone_number: str, otp: int, via_gateway: bool = False) -> None:
    """via_gateway=True submits the code to the SMS gateway (phone login/register OTP only) and
    raises SMSDeliveryError when it is not accepted. Other callers keep the previous behaviour."""
    from django.conf import settings
    if via_gateway and (not settings.DEBUG or Configurations.sms_gateway_url):
        _submit_to_gateway(phone_number, otp)
    elif settings.DEBUG:
        # Local development only: lets a developer read the code without an SMS provider.
        print(f"[SMS] OTP {otp} sent to {phone_number}")
    else:
        logger.info('SMS OTP requested for %s***%s (no SMS gateway configured)', phone_number[:3], phone_number[-2:])


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
