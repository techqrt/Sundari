import logging

import firebase_admin
from django.conf import settings
from firebase_admin import credentials, firestore

from sunndari.config import Configurations

logger = logging.getLogger(__name__)


class FirebaseUtils:
    """Lazy, singleton Firebase Admin SDK access. Initialized on first use
    (not at app startup) so management commands that never touch Firebase
    aren't affected by missing/misconfigured credentials.

    Refuses to initialize under the test runner (settings.TESTING) — Django's
    transaction rollback isolates the SQL side of a test, but Firestore is an
    external service outside that transaction, so unguarded writes from tests
    would land in the real project. Callers (BookingFirebaseUtils,
    NotificationFirebaseUtils) already wrap every call in try/except and log,
    so this raises and is swallowed there, becoming a safe no-op in tests."""

    @staticmethod
    def _ensure_initialized() -> None:
        if settings.TESTING:
            raise RuntimeError('Firebase is disabled under the test runner (settings.TESTING)')
        if not firebase_admin._apps:
            if not Configurations.firebase_credentials_path:
                raise ValueError('FIREBASE_CREDENTIALS_PATH is not configured')
            cred = credentials.Certificate(Configurations.firebase_credentials_path)
            firebase_admin.initialize_app(cred)

    @staticmethod
    def get_client():
        FirebaseUtils._ensure_initialized()
        return firestore.client()


class NotificationFirebaseUtils:
    """Mirrors each Notification row into Firestore under the recipient's own
    user document — users/{user_id}/notifications/{notification_id} — so a
    client can only ever read its own notifications by listening to its own
    uid's subcollection. Best-effort: a Firestore failure never blocks the
    existing DB-backed notification flow (Notification row + NotificationGateway)."""

    COLLECTION = 'users'
    SUBCOLLECTION = 'notifications'

    @staticmethod
    def sync_notification(
        notification_id: int,
        user_id: int,
        type: str,
        title: str,
        message: str,
        booking_id: int = None,
    ) -> None:
        try:
            payload = {
                'notificationId': notification_id,
                'type': type,
                'bookingId': booking_id,
                'title': title,
                'message': message,
                'isRead': False,
                'createdAt': firestore.SERVER_TIMESTAMP,
            }
            (
                FirebaseUtils.get_client()
                .collection(NotificationFirebaseUtils.COLLECTION)
                .document(str(user_id))
                .collection(NotificationFirebaseUtils.SUBCOLLECTION)
                .document(str(notification_id))
                .set(payload)
            )
        except Exception:
            logger.exception('Failed to sync notification %s to Firestore', notification_id)
