from celery import shared_task
from django.utils import timezone
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.payment import Payment


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
