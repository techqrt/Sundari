from django.db import models


class BookingStatus(models.Model):
    status_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'booking_statuses'

    def __str__(self):
        return self.name

    @staticmethod
    def get_all() -> list:
        return list(BookingStatus.objects.all().values('status_id', 'name', 'description'))
