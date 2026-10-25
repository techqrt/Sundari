import json
import logging
import warnings
from django.db import transaction
import pandas
import numpy as np
from sunndari_apps.common.common import Common
from sunndari_apps.notifications.models.notification import Notification
from firebase_admin import messaging
from sunndari_apps.notifications.email_channel import NotificationEmailChannel
from sunndari_apps.notifications.firebase_utils import FirebaseUtils, NotificationFirebaseUtils


logger = logging.getLogger(__name__)


class NotificationGateway:
    """Push delivery through Firebase Cloud Messaging, to the device token the app registered on the user
    (User.fcm_token). The same Firebase project and credentials as the Firestore feed are used. It never
    raises: every outcome comes back as a result dict, and NotificationService records it on the Notification
    row, so a failed push (no token, a dead token, FCM down) is visible but never breaks the caller."""

    @staticmethod
    def send(user_id: int, title: str, message: str, data: dict = None) -> dict:
        from sunndari_apps.authentication.models import User
        token = User.objects.filter(user_id=user_id).values_list('fcm_token', flat=True).first()
        if not token:
            return {'success': False, 'message_id': None, 'reason': 'No device token registered'}
        try:
            FirebaseUtils._ensure_initialized()
            with warnings.catch_warnings():
                # firebase-admin 7.x prefers a Firebase Installation ID (`fid`) and marks `token` deprecated,
                # but the apps register FCM tokens (User.fcm_token), so `token` is what is correct today.
                # Moving to `fid` means the apps send installation IDs instead; until then this one known
                # notice is silenced here only, so any new deprecation elsewhere still shows.
                warnings.filterwarnings('ignore', message='Message.token is deprecated', category=DeprecationWarning)
                push = messaging.Message(
                    token=token,
                    notification=messaging.Notification(title=title, body=message),
                    # FCM data values must be strings; None means "not applicable" and is left out.
                    data={key: str(value) for key, value in (data or {}).items() if value is not None},
                )
            message_id = messaging.send(push)
            return {'success': True, 'message_id': message_id, 'reason': None}
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
            # The app was uninstalled or the token rotated: stop trying it. The app registers a fresh one.
            User.objects.filter(user_id=user_id, fcm_token=token).update(fcm_token=None)
            return {'success': False, 'message_id': None, 'reason': 'Device token is no longer valid; removed'}
        except Exception as error:
            logger.warning('FCM push to user %s failed: %s', user_id, error, exc_info=not isinstance(error, RuntimeError))
            return {'success': False, 'message_id': None, 'reason': str(error)[:300]}


class NotificationService:

    @staticmethod
    def notify(user_id: int, title: str, message: str, type: str = 'generic', booking_id: int = None,
               reference_id: int = None):
        """Best-effort: a notification problem (database, Firestore, push) is logged and swallowed.
        The business action that triggered it has already happened, and reporting it as failed
        (or rolling it back) because a notification could not be written would be worse. The inner
        atomic() is a savepoint so a failed insert cannot poison the caller's transaction."""
        try:
            with transaction.atomic():
                return NotificationService._notify(user_id, title, message, type, booking_id, reference_id)
        except Exception:
            logger.exception('Notification %r for user %s could not be delivered', type, user_id)
            return None

    @staticmethod
    def _notify(user_id: int, title: str, message: str, type: str = 'generic', booking_id: int = None,
                reference_id: int = None) -> int:
        notification_id = Notification().create(
            user_id=user_id, title=title, message=message, type=type, booking_id=booking_id, reference_id=reference_id,
        )
        NotificationFirebaseUtils.sync_notification(
            notification_id=notification_id, user_id=user_id, type=type,
            title=title, message=message, booking_id=booking_id, reference_id=reference_id,
        )
        result = NotificationGateway.send(
            user_id=user_id, title=title, message=message,
            data={'type': type, 'notificationId': notification_id, 'bookingId': booking_id, 'referenceId': reference_id},
        )
        if result['success']:
            Notification.mark_delivery(
                notification_id=notification_id, delivery_status='sent', fcm_message_id=result['message_id'],
            )
        else:
            Notification.mark_delivery(
                notification_id=notification_id, delivery_status='failed', failure_reason=result.get('reason'),
            )
        NotificationEmailChannel.queue(notification_id, type, user_id)
        return notification_id


class NotificationsUtils:
    MAPS = {
        'notification': {
            'notification_id': 'notificationId',
            'user_id': 'userId',
            'booking_id': 'bookingId',
            'reference_id': 'referenceId',
            'type': 'type',
            'title': 'title',
            'message': 'message',
            'is_read': 'isRead',
            'delivery_status': 'deliveryStatus',
            'fcm_message_id': 'fcmMessageId',
            'failure_reason': 'failureReason',
            'sent_at': 'sentAt',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
    }

    def __init__(self, entity: str, columns_required: list = None) -> None:
        self.columns_required = columns_required or []
        self.entity = entity
        self.mapped_columns_name = self.MAPS.get(entity, {})

    @staticmethod
    def flatten_to_nested_dict(df):
        result = []
        df = df.map(
            # pandas.isna() first — a nullable datetime column that also holds a real
            # timestamp gets upcast to datetime64, turning None into NaT, which still
            # has an isoformat() method (returns the literal string "NaT") unless caught here.
            lambda x: None if pandas.isna(x) else (
                x.isoformat() if isinstance(x, (pandas.Timestamp,)) or hasattr(x, 'isoformat') else x
            )
        )
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        for _, row in df.iterrows():
            row_dict = {}
            for col, val in row.items():
                # pandas upcasts an int column to float64 the moment any row in the same
                # frame has a null in it (needs float to hold NaN) — undo that per value,
                # since a plain dict (unlike a DataFrame column) has no dtype to preserve.
                if isinstance(val, float) and not pandas.isna(val) and val.is_integer():
                    val = int(val)
                if '.' in str(col):
                    parts = str(col).split('.')
                    current = row_dict
                    for part in parts[:-1]:
                        current = current.setdefault(part, {})
                    current[parts[-1]] = val
                else:
                    row_dict[col] = val
            result.append(row_dict)
        return result, df

    def mapper(self, data: list) -> str:
        if not data:
            return '[]'
        dataframe = pandas.DataFrame.from_records(data)
        dataframe.rename(columns=self.mapped_columns_name, inplace=True)
        if self.columns_required:
            Common.mapper_value_error(
                mapped_column_names=self.mapped_columns_name,
                columns_required=self.columns_required,
            )
            dataframe = dataframe[self.columns_required]
        flatten_data, _ = self.flatten_to_nested_dict(dataframe)
        return json.dumps(flatten_data, default=str)

    @staticmethod
    def reverse_mapper(entity: str, fields: list) -> dict:
        reverse_map = {v: k for k, v in NotificationsUtils.MAPS.get(entity, {}).items()}
        return {field: reverse_map.get(field, '') for field in fields}
