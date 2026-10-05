from django.db import models
from django.db.models import Q
from django.utils import timezone


class BookingReschedule(models.Model):
    """A request, made by the artist, to move a confirmed booking to a new date/time. The
    booking itself only changes when the customer accepts (and the slot is re-validated at
    that moment). Rows are never deleted: accepted/rejected/cancelled/expired requests stay
    as the audit trail, with the schedule the booking had when the request was made."""

    STATUS_CHOICES = [
        ('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'), ('expired', 'Expired'),
    ]

    reschedule_id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='reschedules',
    )
    requested_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='reschedule_requests',
    )
    previous_date = models.DateField()
    previous_start_time = models.TimeField()
    previous_end_time = models.TimeField()
    proposed_date = models.DateField()
    proposed_start_time = models.TimeField()
    proposed_end_time = models.TimeField()
    reason = models.CharField(max_length=300, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_reschedules'
        constraints = [
            # At most one open request per booking, enforced by the database.
            models.UniqueConstraint(
                fields=['booking'], condition=Q(status='pending'), name='one_pending_reschedule_per_booking',
            ),
        ]
        indexes = [models.Index(fields=['booking', 'status'])]

    def __str__(self):
        return f"Reschedule #{self.reschedule_id} (Booking #{self.booking_id}, {self.status})"

    VALUES_FIELDS = (
        'reschedule_id', 'booking_id', 'requested_by_id',
        'previous_date', 'previous_start_time', 'previous_end_time',
        'proposed_date', 'proposed_start_time', 'proposed_end_time',
        'reason', 'status', 'expires_at', 'responded_at', 'created_at', 'updated_at',
    )

    @staticmethod
    def expire_stale(booking_id: int = None) -> int:
        """Lazily lapses requests nobody answered in time. Called before every read/write
        of reschedules, so correctness never depends on a background job having run."""
        qs = BookingReschedule.objects.filter(status='pending', expires_at__lt=timezone.now())
        if booking_id:
            qs = qs.filter(booking_id=booking_id)
        return qs.update(status='expired', updated_at=timezone.now())

    @staticmethod
    def cancel_pending_for_booking(booking_id: int) -> int:
        return BookingReschedule.objects.filter(booking_id=booking_id, status='pending').update(
            status='cancelled', responded_at=timezone.now(), updated_at=timezone.now(),
        )

    @staticmethod
    def get_all(
        customer_id: int = None,
        artist_id: int = None,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = BookingReschedule.objects.all()
        if customer_id:
            data = data.filter(booking__customer_id=customer_id)
        if artist_id:
            data = data.filter(booking__artist_id=artist_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(reason__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at', '-reschedule_id')
        return list(data.values(*BookingReschedule.VALUES_FIELDS))
