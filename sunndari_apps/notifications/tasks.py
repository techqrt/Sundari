from datetime import datetime, timedelta
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
    upcoming = Booking.objects.filter(
        status__name='confirmed',
        booking_date__range=(now.date(), (now + timedelta(days=2)).date()),
    ).values('booking_id', 'customer_id', 'booking_date', 'start_time')

    sent = {reminder_type: 0 for reminder_type in REMINDER_WINDOWS}
    for booking in upcoming:
        booking_dt = timezone.make_aware(datetime.combine(booking['booking_date'], booking['start_time']))
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
