from datetime import timedelta
import logging
from celery import shared_task
from django.utils import timezone
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.common.emailing import EmailDeliveryError, notification_message, send_email
from sunndari_apps.notifications.email_channel import EMAIL_NOTIFICATION_TYPES
from sunndari_apps.notifications.utils import NotificationService
from sunndari.config import Configurations

logger = logging.getLogger(__name__)

REMINDER_WINDOWS = {
    'booking_reminder_24h': (23.83, 24.17, 'Your appointment is in 24 hours.'),
    'booking_reminder_2h': (1.83, 2.17, 'Your appointment is in 2 hours.'),
}


@shared_task
def send_appointment_reminders() -> dict:
    now = timezone.now()
    # Widened by a day on each side vs. the exact 2-day reminder window: this is only a
    # cheap DB pre-filter, and IST (UTC+5:30) can put a booking's IST calendar date on
    # the other side of the UTC-date boundary near midnight — the real cutoff is the
    # per-booking hours_away check below, computed against the booking's true IST moment.
    upcoming = Booking.objects.filter(
        status__name='confirmed',
        booking_date__range=((now - timedelta(days=1)).date(), (now + timedelta(days=3)).date()),
    ).values('booking_id', 'customer_id', 'booking_date', 'start_time')

    sent = {reminder_type: 0 for reminder_type in REMINDER_WINDOWS}
    for booking in upcoming:
        booking_dt = Booking.to_aware(booking['booking_date'], booking['start_time'])
        hours_away = (booking_dt - now).total_seconds() / 3600

        for reminder_type, (low, high, message) in REMINDER_WINDOWS.items():
            if low <= hours_away <= high and not Notification.exists_for_booking(booking['booking_id'], reminder_type):
                NotificationService.notify(
                    user_id=booking['customer_id'],
                    title='Appointment Reminder',
                    message=message,
                    type=reminder_type,
                    booking_id=booking['booking_id'],
                )
                sent[reminder_type] += 1
    return sent


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_notification_email(self, notification_id: int) -> str:
    """Emails one notification to its user (see notifications/email_channel.py for which types and why). Safe to run
    twice or after a crash: the send is claimed first with an atomic update, so a duplicate does nothing, and the claim
    is handed back if the mail server refuses, so the retry (3 more tries, 2 minutes apart) can finish the job.
    A mail problem never affects the notification itself; it was saved and pushed already."""
    if not Configurations.email_notifications_enabled:
        return 'disabled'
    notification = Notification.objects.select_related('user').filter(pk=notification_id).first()
    if notification is None or notification.type not in EMAIL_NOTIFICATION_TYPES:
        return 'not emailable'
    user = notification.user
    if not user.is_active or not user.email:
        return 'no recipient'
    claimed = Notification.objects.filter(pk=notification_id, email_sent_at__isnull=True).update(email_sent_at=timezone.now())
    if not claimed:
        return 'already sent'
    subject, text, page = notification_message(notification.title, notification.message)
    try:
        send_email(to=user.email, subject=subject, text=text, html_body=page, tag='notification')
    except EmailDeliveryError as error:
        Notification.objects.filter(pk=notification_id).update(email_sent_at=None)
        raise self.retry(exc=error)
    return 'sent'

