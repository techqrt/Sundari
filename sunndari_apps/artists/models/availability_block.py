from django.db import models
from django.utils import timezone


class ArtistAvailabilityBlock(models.Model):
    block_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='availability_blocks',
    )
    block_date = models.DateField()
    note = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'artist_availability_blocks'
        unique_together = ('artist', 'block_date')

    def __str__(self):
        return f"Artist #{self.artist_id} blocked {self.block_date}"

    @staticmethod
    def add(artist_id: int, block_date, note: str = None) -> int:
        obj, _ = ArtistAvailabilityBlock.objects.get_or_create(
            artist_id=artist_id,
            block_date=block_date,
            defaults={'note': note},
        )
        return obj.block_id

    @staticmethod
    def remove(artist_id: int, block_date) -> None:
        ArtistAvailabilityBlock.objects.filter(
            artist_id=artist_id, block_date=block_date,
        ).delete()

    @staticmethod
    def get_all(artist_id: int) -> list:
        return list(
            ArtistAvailabilityBlock.objects.filter(artist_id=artist_id).values(
                'block_id', 'artist_id', 'block_date', 'note', 'created_at',
            )
        )
