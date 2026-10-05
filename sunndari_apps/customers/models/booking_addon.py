from django.db import models


class BookingAddOn(models.Model):
    """What a booking was actually sold with — name, price and duration are copied at
    booking time, so editing or deleting the artist's add-on never rewrites history."""

    booking_addon_id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='addons',
    )
    addon = models.ForeignKey(
        'artists.PackageAddOn',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking_snapshots',
    )
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'booking_addons'
        indexes = [models.Index(fields=['booking'])]

    def __str__(self):
        return f"{self.name} (Booking #{self.booking_id})"

    @staticmethod
    def get_for_bookings(booking_ids: list) -> dict:
        grouped = {}
        for row in BookingAddOn.objects.filter(booking_id__in=booking_ids).order_by('booking_addon_id').values(
            'booking_addon_id', 'booking_id', 'addon_id', 'name', 'price', 'duration_minutes',
        ):
            grouped.setdefault(row['booking_id'], []).append(row)
        return grouped
