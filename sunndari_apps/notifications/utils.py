import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common
from sunndari_apps.notifications.models.notification import Notification


class NotificationGateway:
    """
    Stub push-notification sender. Swap send() for the real firebase-admin
    `messaging.send()` call once an FCM project and credentials are confirmed
    — see Pending Decisions in CHECKLIST.md. Every notify() call still records
    a Notification row regardless, so in-app notification history works today.
    """

    @staticmethod
    def send(user_id: int, title: str, message: str) -> dict:
        return {'success': False, 'message_id': None, 'reason': 'FCM not yet configured'}


class NotificationService:

    @staticmethod
    def notify(user_id: int, title: str, message: str, type: str = 'generic', booking_id: int = None) -> int:
        notification_id = Notification().create(
            user_id=user_id, title=title, message=message, type=type, booking_id=booking_id,
        )
        result = NotificationGateway.send(user_id=user_id, title=title, message=message)
        if result['success']:
            Notification.mark_delivery(
                notification_id=notification_id, delivery_status='sent', fcm_message_id=result['message_id'],
            )
        else:
            Notification.mark_delivery(
                notification_id=notification_id, delivery_status='failed', failure_reason=result.get('reason'),
            )
        return notification_id


class NotificationsUtils:
    MAPS = {
        'notification': {
            'notification_id': 'notificationId',
            'user_id': 'userId',
            'booking_id': 'bookingId',
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
            lambda x: x.isoformat() if isinstance(x, (pandas.Timestamp,)) or hasattr(x, 'isoformat')
            else (None if (isinstance(x, float) and pandas.isna(x)) else x)
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
