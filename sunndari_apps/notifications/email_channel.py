from sunndari.config import Configurations
from sunndari_apps.authentication.models import User
from django.db import transaction

# Transactional notifications about the user's own account or booking, which are normal to receive by email. Left out on
# purpose: anything carrying or prompting a PIN / OTP (a code in an inbox is a risk), high-frequency live updates
# (artist on the way / arrived, service started: push is the right channel), chat messages, and promotional ones such
# as "new service available" (marketing mail needs the customer's opt-in and an unsubscribe link).
EMAIL_NOTIFICATION_TYPES = frozenset({
    'booking_confirmed', 'booking_cancelled', 'booking_completed', 'booking_no_show', 'new_booking_alert',
    'booking_reminder_24h', 'booking_reminder_2h',
    'payment_status', 'refund_initiated', 'refund_pending',
    'reschedule_requested', 'reschedule_accepted', 'reschedule_rejected', 'reschedule_cancelled',
    'artist_approved', 'artist_rejected', 'document_approved', 'document_rejected',
    'brand_request_approved', 'brand_request_rejected', 'payout_account_changed', 'contact_changed',
    'support_ticket_update', 'help_center_admin_reply', 'review_reply',
})


class NotificationEmailChannel:
    """Sends the email copy of a notification, in the background, for users who have an email address."""

    @staticmethod
    def wants_email(type: str, user_id: int) -> bool:
        if not Configurations.email_notifications_enabled or type not in EMAIL_NOTIFICATION_TYPES:
            return False
        return bool(User.objects.filter(user_id=user_id, is_active=True).exclude(email__isnull=True).exclude(email='').exists())

    @staticmethod
    def queue(notification_id: int, type: str, user_id: int) -> None:
        """Queued only after the notification is committed, so the job always finds it, and never raises."""
        if not NotificationEmailChannel.wants_email(type, user_id):
            return
        from sunndari_apps.common.queueing import enqueue
        from sunndari_apps.notifications.tasks import send_notification_email
        transaction.on_commit(lambda: enqueue(send_notification_email, notification_id))
