from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.models.booking_addon import BookingAddOn


class BookingExtras:
    """Adds the fields that live outside Booking.VALUES_FIELDS to mapped booking rows.

    The customer and the artist see the same booking, but not the same numbers: the artist
    additionally gets the platform fee / net amount / travel buffers. Those are the artist's
    own earnings figures and are never returned to the customer."""

    CUSTOMER_COLUMNS = {'travelFee': 'travel_fee'}
    ARTIST_COLUMNS = {
        'travelFee': 'travel_fee',
        'platformFee': 'platform_fee',
        'netAmount': 'net_amount',
        'travelMinutesBefore': 'travel_minutes_before',
        'returnBufferMinutes': 'return_buffer_minutes',
    }
    ADDONS_COLUMN = 'addOns'

    @classmethod
    def extra_names(cls, for_artist: bool) -> set:
        return set((cls.ARTIST_COLUMNS if for_artist else cls.CUSTOMER_COLUMNS)) | {cls.ADDONS_COLUMN}

    @classmethod
    def split_columns(cls, columns: list, for_artist: bool):
        """(columns for the pandas mapper, extra columns) — mapper keeps raising on unknown names."""
        extras = cls.extra_names(for_artist)
        mapper_columns = [column for column in columns if column not in extras]
        extra_columns = [column for column in columns if column in extras]
        if columns and not mapper_columns:
            mapper_columns = ['bookingId']
        return mapper_columns, extra_columns

    @staticmethod
    def _money(value):
        return None if value is None else f'{value:.2f}'

    @classmethod
    def attach(cls, raw_rows: list, mapped_rows: list, for_artist: bool, only: list = None) -> list:
        if not raw_rows:
            return mapped_rows
        columns = cls.ARTIST_COLUMNS if for_artist else cls.CUSTOMER_COLUMNS
        wanted = set(only) if only else None
        booking_ids = [row['booking_id'] for row in raw_rows]
        stored = {
            row['booking_id']: row
            for row in Booking.objects.filter(booking_id__in=booking_ids).values('booking_id', *columns.values())
        }
        addons = BookingAddOn.get_for_bookings(booking_ids)
        for raw, data in zip(raw_rows, mapped_rows):
            row = stored.get(raw['booking_id'], {})
            for api_name, field in columns.items():
                if wanted is not None and api_name not in wanted:
                    continue
                value = row.get(field)
                data[api_name] = cls._money(value) if field in ('travel_fee', 'platform_fee', 'net_amount') else value
            if wanted is None or cls.ADDONS_COLUMN in wanted:
                data[cls.ADDONS_COLUMN] = [
                    {'addOnId': item['addon_id'], 'name': item['name'],
                     'price': cls._money(item['price']), 'durationMinutes': item['duration_minutes']}
                    for item in addons.get(raw['booking_id'], [])
                ]
        return mapped_rows
