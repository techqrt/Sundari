import logging

from sunndari_apps.notifications.firebase_utils import FirebaseUtils
from sunndari_apps.customers.models.booking import Booking

logger = logging.getLogger(__name__)


class BookingFirebaseUtils:
    """Mirrors booking state into Firestore's top-level `bookings` collection
    (document id = booking_id) so the Flutter app can read live booking
    status directly. Best-effort: a Firestore failure never blocks the
    booking flow — the SQL `Booking` row stays the source of truth.

    Builds the payload field-by-field (rather than reusing CustomersUtils.mapper,
    which flattens everything to JSON strings for the REST API) so numeric and
    timestamp fields keep their native Firestore types (number / Timestamp)."""

    COLLECTION = 'bookings'

    @staticmethod
    def _build_payload(booking: dict) -> dict:
        total_amount = booking.get('total_amount')
        start_time = booking.get('start_time')
        end_time = booking.get('end_time')
        booking_date = booking.get('booking_date')
        return {
            'bookingId': booking['booking_id'],
            'customerId': booking['customer_id'],
            'artistId': booking['artist_id'],
            'subCategoryId': booking['sub_category_id'],
            'packageId': booking['package_id'],
            'locationTypeId': booking['location_type_id'],
            'addressId': booking.get('address_id'),
            'bookingDate': booking_date.isoformat() if booking_date else None,
            'startTime': start_time.strftime('%H:%M') if start_time else None,
            'endTime': end_time.strftime('%H:%M') if end_time else None,
            'statusId': booking['status_id'],
            'totalAmount': float(total_amount) if total_amount is not None else None,
            'notes': booking.get('notes'),
            'cancelledBy': booking.get('cancelled_by'),
            'cancellationReason': booking.get('cancellation_reason'),
            'expiresAt': booking.get('expires_at'),
            'createdAt': booking.get('created_at'),
            'updatedAt': booking.get('updated_at'),
        }

    @staticmethod
    def sync_booking(booking_id: int) -> None:
        try:
            booking = Booking.get(booking_id=booking_id)
            if not booking:
                return
            payload = BookingFirebaseUtils._build_payload(booking)
            FirebaseUtils.get_client().collection(BookingFirebaseUtils.COLLECTION).document(
                str(booking_id)
            ).set(payload, merge=True)
        except Exception:
            logger.exception('Failed to sync booking %s to Firestore', booking_id)
