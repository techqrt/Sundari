from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService

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
