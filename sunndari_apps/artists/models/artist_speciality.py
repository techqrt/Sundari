from django.db import models
from django.utils import timezone


class ArtistSpeciality(models.Model):
    """A service the artist is *specialised* in. Distinct from ArtistServiceOffering (what
    the artist offers): specialities are always a subset of the offered services, enforced by
    the API and by ArtistServiceOffering.remove()."""

    speciality_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='specialities',
    )
    sub_category = models.ForeignKey(
        'core.ServiceSubCategory',
        on_delete=models.CASCADE,
        related_name='artist_specialities',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'artist_specialities'
        unique_together = ('artist', 'sub_category')

    def __str__(self):
        return f"Artist #{self.artist_id} speciality {self.sub_category_id}"

    @staticmethod
    def replace_for_artist(artist_id: int, sub_category_ids: list) -> None:
        wanted = set(sub_category_ids)
        ArtistSpeciality.objects.filter(artist_id=artist_id).exclude(sub_category_id__in=wanted).delete()
        existing = set(
            ArtistSpeciality.objects.filter(artist_id=artist_id).values_list('sub_category_id', flat=True)
        )
        ArtistSpeciality.objects.bulk_create([
            ArtistSpeciality(artist_id=artist_id, sub_category_id=sub_id) for sub_id in wanted - existing
        ])

    @staticmethod
    def get_all(artist_id: int) -> list:
        return list(
            ArtistSpeciality.objects.filter(artist_id=artist_id).order_by('sub_category_id').values(
                'sub_category_id', 'sub_category__name',
            )
        )
