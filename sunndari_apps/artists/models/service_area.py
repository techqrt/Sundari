from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class ArtistServiceArea(models.Model):
    """A city the artist travels to, and what (if anything) they charge for travelling there.
    Applied server-side to Home Visit bookings (customers.CreateBookingView); an artist with
    no service areas configured keeps the previous behaviour (no restriction, no charge)."""

    TRAVEL_CHARGE_CHOICES = [('free', 'Free'), ('per_visit', 'Per visit'), ('per_km', 'Per kilometre')]

    area_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='service_areas',
    )
    city = models.CharField(max_length=100)
    travel_charge_type = models.CharField(max_length=10, choices=TRAVEL_CHARGE_CHOICES, default='free')
    charge_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_service_areas'
        constraints = [
            models.UniqueConstraint(Lower('city'), 'artist', name='unique_service_area_city_per_artist'),
        ]

    def __str__(self):
        return f"{self.city} (Artist #{self.artist_id}, {self.travel_charge_type})"

    VALUES_FIELDS = (
        'area_id', 'artist_id', 'city', 'travel_charge_type', 'charge_amount',
        'is_active', 'created_at', 'updated_at',
    )

    @staticmethod
    def city_exists(artist_id: int, city: str, exclude_area_id: int = None) -> bool:
        qs = ArtistServiceArea.objects.filter(artist_id=artist_id, city__iexact=city.strip())
        if exclude_area_id:
            qs = qs.exclude(area_id=exclude_area_id)
        return qs.exists()

    def create(self, artist_id: int, city: str, travel_charge_type: str, charge_amount=0) -> int:
        self.artist_id = artist_id
        self.city = city.strip()
        self.travel_charge_type = travel_charge_type
        self.charge_amount = charge_amount
        self.save()
        return self.area_id

    @staticmethod
    def update(area_id: int, city: str = None, travel_charge_type: str = None, charge_amount=None,
               is_active: bool = None) -> None:
        area = ArtistServiceArea.objects.get(area_id=area_id)
        if city is not None:
            area.city = city.strip()
        if travel_charge_type is not None:
            area.travel_charge_type = travel_charge_type
        if charge_amount is not None:
            area.charge_amount = charge_amount
        if is_active is not None:
            area.is_active = is_active
        area.save()

    @staticmethod
    def remove(area_id: int) -> None:
        ArtistServiceArea.objects.get(area_id=area_id).delete()

    @staticmethod
    def get(area_id: int) -> dict:
        return ArtistServiceArea.objects.filter(area_id=area_id).values(*ArtistServiceArea.VALUES_FIELDS).first()

    @staticmethod
    def get_all(artist_id: int, only_active: bool = False) -> list:
        qs = ArtistServiceArea.objects.filter(artist_id=artist_id)
        if only_active:
            qs = qs.filter(is_active=True)
        return list(qs.order_by('area_id').values(*ArtistServiceArea.VALUES_FIELDS))

    @staticmethod
    def find_for_city(artist_id: int, city: str):
        return ArtistServiceArea.objects.filter(
            artist_id=artist_id, is_active=True, city__iexact=(city or '').strip(),
        ).first()

    @staticmethod
    def has_active(artist_id: int) -> bool:
        return ArtistServiceArea.objects.filter(artist_id=artist_id, is_active=True).exists()
