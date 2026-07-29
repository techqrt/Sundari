from django.db import models
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta


class Booking(models.Model):
    CANCELLED_BY_CHOICES = [('customer', 'Customer'), ('artist', 'Artist')]

    ACTIVE_STATUSES = ['pending', 'confirmed', 'in_progress']

    ARTIST_TRANSITIONS = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['in_progress', 'cancelled'],
        'in_progress': ['completed', 'no_show'],
    }

    booking_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='bookings_as_customer',
    )
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    sub_category = models.ForeignKey(
        'core.ServiceSubCategory',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    package = models.ForeignKey(
        'artists.PricingPackage',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    location_type = models.ForeignKey(
        'core.LocationType',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    address = models.ForeignKey(
        'users.CustomerAddress',
        on_delete=models.PROTECT,
        related_name='bookings',
        null=True,
        blank=True,
    )
    booking_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.ForeignKey(
        'core.BookingStatus',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=10, choices=CANCELLED_BY_CHOICES, null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bookings'
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['artist']),
            models.Index(fields=['booking_date']),
        ]

    def __str__(self):
        return f"Booking #{self.booking_id} (Customer #{self.customer_id} → Artist #{self.artist_id})"

    VALUES_FIELDS = (
        'booking_id', 'customer_id', 'artist_id', 'sub_category_id', 'package_id',
        'location_type_id', 'address_id', 'booking_date', 'start_time', 'end_time',
        'status_id', 'total_amount', 'notes', 'cancelled_by', 'cancellation_reason',
        'expires_at', 'created_at', 'updated_at',
    )

    def create(
        self,
        customer_id: int,
        artist_id: int,
        sub_category_id: int,
        package_id: int,
        location_type_id: int,
        booking_date,
        start_time,
        end_time,
        status_id: int,
        total_amount,
        address_id: int = None,
        notes: str = None,
        lock_minutes: int = 15,
    ) -> int:
        self.customer_id = customer_id
        self.artist_id = artist_id
        self.sub_category_id = sub_category_id
        self.package_id = package_id
        self.location_type_id = location_type_id
        self.address_id = address_id
        self.booking_date = booking_date
        self.start_time = start_time
        self.end_time = end_time
        self.status_id = status_id
        self.total_amount = total_amount
        self.notes = notes
        self.expires_at = timezone.now() + timedelta(minutes=lock_minutes)
        self.save()
        return self.booking_id

    @staticmethod
    def get(booking_id: int) -> dict:
        return Booking.objects.filter(booking_id=booking_id).values(*Booking.VALUES_FIELDS).first()

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
        data = Booking.objects.all()
        if customer_id:
            data = data.filter(customer_id=customer_id)
        if artist_id:
            data = data.filter(artist_id=artist_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(notes__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*Booking.VALUES_FIELDS))

    @staticmethod
    def has_overlap(artist_id: int, booking_date, start_time, end_time, exclude_booking_id: int = None) -> bool:
        qs = Booking.objects.filter(
            artist_id=artist_id,
            booking_date=booking_date,
            status__name__in=Booking.ACTIVE_STATUSES,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_booking_id:
            qs = qs.exclude(booking_id=exclude_booking_id)
        return qs.exists()

    @staticmethod
    def get_booked_ranges(artist_id: int, booking_date) -> list:
        return list(
            Booking.objects.filter(
                artist_id=artist_id,
                booking_date=booking_date,
                status__name__in=Booking.ACTIVE_STATUSES,
            ).values('start_time', 'end_time')
        )

    @staticmethod
    def update_status(
        booking_id: int,
        status_id: int,
        cancelled_by: str = None,
        cancellation_reason: str = None,
    ) -> None:
        booking = Booking.objects.get(booking_id=booking_id)
        booking.status_id = status_id
        if cancelled_by is not None:
            booking.cancelled_by = cancelled_by
        if cancellation_reason is not None:
            booking.cancellation_reason = cancellation_reason
        booking.save()
