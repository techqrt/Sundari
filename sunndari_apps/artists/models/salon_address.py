from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class ArtistSalonAddress(models.Model):
    """A salon or studio the artist works from, which a customer picks when booking an In-Salon appointment.

    Kept apart from users.CustomerAddress on purpose: that model is a person's own address (no name, no coordinates)
    and is what an artist's own "my addresses" list shows, so mixing business locations into it would blur the two.
    An address is never hard-deleted once a booking points at it; it is switched off (is_active=False) instead, so
    history keeps its place. Only active addresses count towards the limit and the name rule, and only active ones
    are shown to customers."""

    MAX_ACTIVE_PER_ARTIST = 10

    salon_address_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='salon_addresses',
    )
    # What the customer sees in the list, e.g. "Gomti Nagar Studio".
    name = models.CharField(max_length=100)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=10)
    # Degrees with six decimals (about 10 cm). Both are always set: customers navigate by them.
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_salon_addresses'
        indexes = [models.Index(fields=['artist', 'is_active'])]
        constraints = [
            # One live address per name for an artist (ignoring case); a switched-off address frees its name.
            models.UniqueConstraint(
                Lower('name'), 'artist', condition=Q(is_active=True), name='unique_active_salon_name_per_artist',
            ),
            # The database refuses an impossible position even if a caller skips the serializer.
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90, longitude__gte=-180, longitude__lte=180),
                name='salon_address_coordinates_in_range',
            ),
        ]

    def __str__(self):
        return f"{self.name} (Artist #{self.artist_id})"

    @staticmethod
    def active_count(artist_id: int) -> int:
        return ArtistSalonAddress.objects.filter(artist_id=artist_id, is_active=True).count()

    @staticmethod
    def name_exists(artist_id: int, name: str, exclude_salon_address_id: int = None) -> bool:
        """Whether the artist already has an active address with this name (ignoring case and surrounding spaces)."""
        qs = ArtistSalonAddress.objects.filter(artist_id=artist_id, is_active=True, name__iexact=name.strip())
        if exclude_salon_address_id:
            qs = qs.exclude(salon_address_id=exclude_salon_address_id)
        return qs.exists()

    @staticmethod
    def get_all_active(artist_id: int) -> list:
        """The artist's live addresses in the order they were added. Coordinates are plain numbers (six decimals
        are exact in a float) so a map can use them as they are."""
        rows = ArtistSalonAddress.objects.filter(artist_id=artist_id, is_active=True).order_by('salon_address_id')
        return [
            {
                'salon_address_id': row.salon_address_id, 'name': row.name, 'address_line_1': row.address_line_1,
                'address_line_2': row.address_line_2, 'city': row.city, 'pin_code': row.pin_code,
                'latitude': float(row.latitude), 'longitude': float(row.longitude),
                'created_at': row.created_at.isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    def get_active_owned(artist_id: int, salon_address_id: int):
        """The artist's own live address, or None (also None for someone else's or a switched-off one)."""
        return ArtistSalonAddress.objects.filter(
            salon_address_id=salon_address_id, artist_id=artist_id, is_active=True,
        ).first()

    def booking_snapshot(self) -> dict:
        """What a booking keeps of this address, so later edits or deletion never change the booking."""
        return {
            'salon_address_id': self.salon_address_id, 'name': self.name, 'address_line_1': self.address_line_1,
            'address_line_2': self.address_line_2, 'city': self.city, 'pin_code': self.pin_code,
            'latitude': float(self.latitude), 'longitude': float(self.longitude),
        }

    def deactivate(self) -> None:
        """Delete from the artist's point of view. The row is kept (is_active=False), never removed, so a booking
        that points at it keeps its place in history; it frees the name and one of the 10 slots, and customers
        stop seeing it."""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def update_fields(self, **fields) -> None:
        """Apply the given changes (text is trimmed; an empty address_line_2 clears it) and save."""
        for key, value in fields.items():
            if isinstance(value, str):
                value = value.strip()
            if key == 'address_line_2':
                value = value or None
            setattr(self, key, value)
        self.save()

    def create(
        self, artist_id: int, name: str, address_line_1: str, city: str, pin_code: str,
        latitude, longitude, address_line_2: str = None,
    ) -> int:
        self.artist_id = artist_id
        self.name = name.strip()
        self.address_line_1 = address_line_1.strip()
        self.address_line_2 = (address_line_2 or '').strip() or None
        self.city = city.strip()
        self.pin_code = pin_code.strip()
        self.latitude = latitude
        self.longitude = longitude
        self.save()
        return self.salon_address_id
