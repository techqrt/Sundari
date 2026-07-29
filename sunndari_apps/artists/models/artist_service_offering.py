from django.db import models
from django.utils import timezone


class ArtistServiceOffering(models.Model):
    offering_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='service_offerings',
    )
    sub_category = models.ForeignKey(
        'core.ServiceSubCategory',
        on_delete=models.PROTECT,
        related_name='artist_offerings',
    )
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    custom_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'artist_service_offerings'
        unique_together = ('artist', 'sub_category')

    def __str__(self):
        return f"Artist #{self.artist_id} → {self.sub_category_id}"

    @staticmethod
    def add(artist_id: int, sub_category_id: int, custom_price=None, custom_duration_minutes=None) -> int:
        obj, _ = ArtistServiceOffering.objects.get_or_create(
            artist_id=artist_id,
            sub_category_id=sub_category_id,
            defaults={
                'custom_price': custom_price,
                'custom_duration_minutes': custom_duration_minutes,
                'is_active': True,
            },
        )
        return obj.offering_id

    @staticmethod
    def remove(artist_id: int, sub_category_id: int) -> None:
        ArtistServiceOffering.objects.filter(
            artist_id=artist_id,
            sub_category_id=sub_category_id,
        ).delete()

    @staticmethod
    def get_all(artist_id: int) -> list:
        return list(
            ArtistServiceOffering.objects.filter(artist_id=artist_id).values(
                'offering_id', 'artist_id', 'sub_category_id',
                'custom_price', 'custom_duration_minutes', 'is_active', 'created_at',
            )
        )

    @staticmethod
    def exists(artist_id: int, sub_category_id: int) -> bool:
        return ArtistServiceOffering.objects.filter(
            artist_id=artist_id, sub_category_id=sub_category_id,
        ).exists()
