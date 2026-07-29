from django.db import models


class ArtistAvailabilitySchedule(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]

    schedule_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='availability_schedules',
    )
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    location_type = models.ForeignKey(
        'core.LocationType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'artist_availability_schedules'
        unique_together = ('artist', 'day_of_week')

    def __str__(self):
        return f"Artist #{self.artist_id} — day {self.day_of_week} {self.start_time}–{self.end_time}"

    def set(self, artist_id: int, day_of_week: int, start_time, end_time, location_type_id: int = None) -> int:
        obj, _ = ArtistAvailabilitySchedule.objects.update_or_create(
            artist_id=artist_id,
            day_of_week=day_of_week,
            defaults={
                'start_time': start_time,
                'end_time': end_time,
                'location_type_id': location_type_id,
                'is_active': True,
            },
        )
        return obj.schedule_id

    @staticmethod
    def remove(artist_id: int, day_of_week: int) -> None:
        ArtistAvailabilitySchedule.objects.filter(
            artist_id=artist_id, day_of_week=day_of_week,
        ).delete()

    @staticmethod
    def get_all(artist_id: int) -> list:
        return list(
            ArtistAvailabilitySchedule.objects.filter(artist_id=artist_id).values(
                'schedule_id', 'artist_id', 'day_of_week',
                'start_time', 'end_time', 'location_type_id', 'is_active',
            )
        )
