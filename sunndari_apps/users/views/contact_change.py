import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import send_otp_sms, send_otp_email
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants

OTP_VALID_MINUTES = 10
MIN_SECONDS_BETWEEN_REQUESTS = 60
MAX_ATTEMPTS = 5


class ContactChangeView:
    """Changing the email / phone number on an account requires a code sent to the NEW
    contact, so a stolen session token alone can't redirect the account's recovery channel."""

    @staticmethod
    def _clear_pending(user: User) -> None:
        user.pending_email = None
        user.pending_phone_number = None
        user.contact_otp = None
        user.contact_otp_expiry = None
        user.contact_otp_attempts = 0

    @Common().exception_handler
    def request_extract(self, params):
        with transaction.atomic():
            user = User.objects.select_for_update().get(user_id=params.user_id)
            now = timezone.now()
            if user.contact_otp_requested_at and (now - user.contact_otp_requested_at).total_seconds() < MIN_SECONDS_BETWEEN_REQUESTS:
                raise ValueError(Constants.contact_change_wait)
            if params.email:
                if params.email == user.email:
                    raise ValueError(Constants.contact_change_same)
                if User.objects.filter(email=params.email).exclude(user_id=user.user_id).exists():
                    raise ValueError(Constants.email_not_unique)
            else:
                if params.phone_number == user.phone_number:
                    raise ValueError(Constants.contact_change_same)
                if User.objects.filter(phone_number=params.phone_number).exclude(user_id=user.user_id).exists():
                    raise ValueError(Constants.mobile_number_not_unique)
            otp = random.randint(100000, 999999)
            self._clear_pending(user)
            user.pending_email = params.email
            user.pending_phone_number = params.phone_number
            user.contact_otp = otp
            user.contact_otp_expiry = now + timedelta(minutes=OTP_VALID_MINUTES)
            user.contact_otp_requested_at = now
            user.save()
        # Sent to the NEW contact, after the state is committed.
        if params.email:
            send_otp_email(params.email, otp)
        else:
            send_otp_sms(params.phone_number, otp)
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.otp_sent))

    @Common().exception_handler
    def verify_extract(self, params):
        failure = None
        with transaction.atomic():
            user = User.objects.select_for_update().get(user_id=params.user_id)
            pending = user.pending_email or user.pending_phone_number
            if not pending or user.contact_otp is None:
                failure = Constants.contact_change_invalid
            elif not user.contact_otp_expiry or timezone.now() > user.contact_otp_expiry:
                self._clear_pending(user)
                user.save()
                failure = Constants.contact_change_invalid
            elif user.contact_otp != int(params.otp):
                user.contact_otp_attempts += 1
                if user.contact_otp_attempts >= MAX_ATTEMPTS:
                    # The code is burned after too many guesses — a fresh one must be requested.
                    self._clear_pending(user)
                    failure = Constants.contact_change_locked
                else:
                    failure = Constants.contact_change_invalid
                user.save()
            else:
                if user.pending_email and User.objects.filter(email=user.pending_email).exclude(user_id=user.user_id).exists():
                    self._clear_pending(user)
                    user.save()
                    failure = Constants.email_not_unique
                elif user.pending_phone_number and User.objects.filter(
                    phone_number=user.pending_phone_number,
                ).exclude(user_id=user.user_id).exists():
                    self._clear_pending(user)
                    user.save()
                    failure = Constants.mobile_number_not_unique
                else:
                    changed = 'email' if user.pending_email else 'phone number'
                    if user.pending_email:
                        user.email = user.pending_email
                    else:
                        user.phone_number = user.pending_phone_number
                    # Single use: the code and the pending value are gone the moment they work.
                    self._clear_pending(user)
                    user.save()
        # Raised only after the transaction committed, so a wrong guess still counts.
        if failure:
            raise ValueError(failure)
        NotificationService.notify(
            user_id=params.user_id, title='Contact details changed',
            message=f'Your {changed} was changed. If this was not you, contact support.',
            type='contact_changed',
        )
        return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=f'Your {changed} was updated'))
