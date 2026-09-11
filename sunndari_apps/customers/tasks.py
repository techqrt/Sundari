from celery import shared_task
from django.utils import timezone
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.customers.models.booking import Booking, IST
from sunndari_apps.payments.models import Payment
from sunndari_apps.notifications.utils import NotificationService


@shared_task
def cancel_stale_pending_bookings() -> int:
    cancelled_status = BookingStatus.objects.filter(name='cancelled').first()
    if not cancelled_status:
        return 0
    stale = Booking.objects.filter(
        status__name='pending',
        expires_at__lt=timezone.now(),
    ).exclude(
        booking_id__in=Payment.objects.filter(status__name='paid').values('booking_id'),
    )
    return stale.update(
        status_id=cancelled_status.status_id,
        cancellation_reason='Auto-cancelled: slot lock expired without confirmation',
        updated_at=timezone.now(),
    )


@shared_task
def mark_missed_bookings() -> int:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). A pending/confirmed booking
    whose scheduled window (bookingDate + startTime + grace) has elapsed with nobody
    acting on it becomes 'no_show' — the single backend-authoritative source of truth,
    so the customer app, artist app, and reports never disagree on whether a booking is
    still active. Deliberately excludes 'in_progress': once the Start PIN has actually
    been verified in person, the service should be allowed to run to completion no
    matter how long it takes, rather than getting swept out from under an artist who is
    still on-site."""
    no_show_status = BookingStatus.objects.filter(name='no_show').first()
    if not no_show_status:
        return 0

    today_ist = timezone.now().astimezone(IST).date()
    candidates = Booking.objects.filter(
        status__name__in=['pending', 'confirmed'],
        booking_date__lte=today_ist,
    ).values('booking_id', 'customer_id', 'booking_date', 'start_time')

    missed_count = 0
    for booking in candidates:
        if Booking.is_past_missed_deadline(booking['booking_date'], booking['start_time']):
            Booking.mark_missed(booking_id=booking['booking_id'], no_show_status_id=no_show_status.status_id)
            NotificationService.notify(
                user_id=booking['customer_id'],
                title='Booking missed',
                message=f"Your booking on {booking['booking_date']} was not completed in time and has been marked as missed.",
                type='booking_no_show',
                booking_id=booking['booking_id'],
            )
            missed_count += 1
    return missed_count
