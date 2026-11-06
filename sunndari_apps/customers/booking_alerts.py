import logging

from sunndari_apps.authentication.utils import send_otp_email, send_otp_sms
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService

logger = logging.getLogger(__name__)


def notify_artist_booking_paid(booking_id: int) -> None:
    """Tell the artist about a new booking, but only once it has been paid for: until then the booking is
    invisible to them. Safe to call from every payment path and more than once; the artist hears about a
    booking a single time."""
    try:
        booking = Booking.objects.select_related('artist__user').filter(booking_id=booking_id).first()
        if not booking or not Booking.objects.filter(booking_id=booking_id).filter(Booking.artist_visible_filter()).exists():
            return
        if Notification.exists_for_booking(booking_id, 'new_booking_alert'):
            return
        artist_user = booking.artist.user
        NotificationService.notify(
            user_id=artist_user.user_id,
            title='New booking request',
            message=f'You have a new booking request for {booking.booking_date}.',
            type='new_booking_alert',
            booking_id=booking_id,
        )
        if booking.booking_otp:
            if artist_user.phone_number:
                send_otp_sms(artist_user.phone_number, booking.booking_otp)
            elif artist_user.email:
                send_otp_email(artist_user.email, booking.booking_otp)
    except Exception:
        logger.exception('Could not notify the artist of paid booking %s', booking_id)
