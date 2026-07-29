from django.db import models


class ArtistLocationPreference(models.Model):
    preference_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='location_preferences',
    )
    location_type = models.ForeignKey(
        'core.LocationType',
        on_delete=models.PROTECT,
        related_name='artist_preferences',
    )

    class Meta:
        db_table = 'artist_location_preferences'
        unique_together = ('artist', 'location_type')

    def __str__(self):
        return f"Artist #{self.artist_id} → {self.location_type_id}"

    @staticmethod
    def add(artist_id: int, location_type_id: int) -> int:
        obj, _ = ArtistLocationPreference.objects.get_or_create(
            artist_id=artist_id,
            location_type_id=location_type_id,
        )
        return obj.preference_id

    @staticmethod
    def remove(artist_id: int, location_type_id: int) -> None:
        ArtistLocationPreference.objects.filter(
            artist_id=artist_id,
            location_type_id=location_type_id,
        ).delete()

    @staticmethod
    def get_all(artist_id: int) -> list:
        return list(
            ArtistLocationPreference.objects.filter(artist_id=artist_id).values(
                'preference_id', 'artist_id', 'location_type_id',
            )
        )
