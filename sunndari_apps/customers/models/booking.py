import random
from datetime import datetime, timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Booking(models.Model):
    CANCELLED_BY_CHOICES = [('customer', 'Customer'), ('artist', 'Artist')]

    ACTIVE_STATUSES = ['pending', 'confirmed', 'in_progress']

    # 'in_progress' is deliberately absent from 'confirmed', and 'completed' from
    # 'in_progress' — those moves are only reachable through the Start Service PIN and
    # Completion PIN verification endpoints now.
    ARTIST_TRANSITIONS = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['cancelled'],
        'in_progress': ['no_show'],
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

    # Booking OTP — generated right after booking creation, delivered to the artist.
    # Verified by the artist as part of the "I've Arrived" action (proves the artist
    # holds the correct booking-issued credential before arrival is accepted).
    booking_otp = models.IntegerField(null=True, blank=True)
    booking_otp_expiry = models.DateTimeField(null=True, blank=True)
    booking_otp_attempts = models.IntegerField(default=0)
    booking_otp_locked_until = models.DateTimeField(null=True, blank=True)
    booking_otp_verified_at = models.DateTimeField(null=True, blank=True)

    # On-my-way / arrival sub-stage timestamps. Status stays 'confirmed' across these —
    # the sub-stage is derived from which of these timestamps is set.
    on_my_way_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)

    # Start Service PIN — generated on arrival, shown to the customer, entered by the
    # artist to transition the booking into 'in_progress'.
    start_service_pin = models.IntegerField(null=True, blank=True)
    start_pin_expiry = models.DateTimeField(null=True, blank=True)
    start_pin_attempts = models.IntegerField(default=0)
    start_pin_locked_until = models.DateTimeField(null=True, blank=True)
    service_started_at = models.DateTimeField(null=True, blank=True)

    # Completion PIN — generated once service starts, shown to the customer, entered
    # by the artist to transition the booking into 'completed'.
    completion_pin = models.IntegerField(null=True, blank=True)
    completion_pin_expiry = models.DateTimeField(null=True, blank=True)
    completion_pin_attempts = models.IntegerField(default=0)
    completion_pin_locked_until = models.DateTimeField(null=True, blank=True)
    service_completed_at = models.DateTimeField(null=True, blank=True)

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

    # Backend-internal only — deliberately excluded from VALUES_FIELDS/CustomersUtils.MAPS
    # so the lifecycle-credential fields (OTP/PINs) never flow through the public
    # get/get_all booking endpoints, no matter what `values`/columns filter is requested.
    LIFECYCLE_FIELDS = (
        'booking_id', 'customer_id', 'artist_id', 'status_id', 'booking_date',
        'start_time', 'end_time',
        'booking_otp', 'booking_otp_expiry', 'booking_otp_attempts',
        'booking_otp_locked_until', 'booking_otp_verified_at',
        'on_my_way_at', 'arrived_at',
        'start_service_pin', 'start_pin_expiry', 'start_pin_attempts',
        'start_pin_locked_until', 'service_started_at',
        'completion_pin', 'completion_pin_expiry', 'completion_pin_attempts',
        'completion_pin_locked_until', 'service_completed_at',
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
    def get_lifecycle_state(booking_id: int) -> dict:
        return Booking.objects.filter(booking_id=booking_id).values(*Booking.LIFECYCLE_FIELDS).first()

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
    def generate_booking_otp(booking_id: int, booking_date, end_time, buffer_hours: int = 2) -> int:
        """Generated once, right after booking creation. Stays valid through the whole
        upcoming/on-my-way window and is verified by the artist as part of "I've Arrived" —
        so its expiry is tied to the appointment's own scheduled end (+ a running-late
        buffer), not a short fixed window like the login OTP."""
        otp = random.randint(100000, 999999)
        expiry = timezone.make_aware(datetime.combine(booking_date, end_time)) + timedelta(hours=buffer_hours)
        booking = Booking.objects.get(booking_id=booking_id)
        booking.booking_otp = otp
        booking.booking_otp_expiry = expiry
        booking.booking_otp_attempts = 0
        booking.booking_otp_locked_until = None
        booking.booking_otp_verified_at = None
        booking.save()
        return otp

    @staticmethod
    def is_booking_otp_locked(booking_id: int) -> bool:
        """Mirrors User.is_locked_out(): same 5-attempt / 30-minute lockout convention,
        auto-clearing the lock once it has expired."""
        booking = Booking.objects.get(booking_id=booking_id)
        if booking.booking_otp_locked_until and timezone.now() < booking.booking_otp_locked_until:
            return True
        if booking.booking_otp_locked_until and timezone.now() >= booking.booking_otp_locked_until:
            booking.booking_otp_locked_until = None
            booking.booking_otp_attempts = 0
            booking.save()
        return False

    @staticmethod
    def record_booking_otp_failure(booking_id: int, max_attempts: int = 5, lockout_minutes: int = 30) -> None:
        booking = Booking.objects.get(booking_id=booking_id)
        booking.booking_otp_attempts += 1
        if booking.booking_otp_attempts >= max_attempts:
            booking.booking_otp_locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        booking.save()

    @staticmethod
    def confirm_arrival(booking_id: int, booking_date, end_time, buffer_hours: int = 2) -> int:
        """Called only after the Booking OTP has already been validated by the caller.
        Consumes the Booking OTP (single-use — cleared here, not just flagged) and mints
        the Start Service PIN in the same write. PIN expiry mirrors the Booking OTP's own
        policy: valid through the rest of the scheduled slot plus a running-late buffer."""
        pin = random.randint(1000, 9999)
        expiry = timezone.make_aware(datetime.combine(booking_date, end_time)) + timedelta(hours=buffer_hours)
        booking = Booking.objects.get(booking_id=booking_id)
        booking.arrived_at = timezone.now()
        booking.booking_otp = None
        booking.booking_otp_expiry = None
        booking.booking_otp_attempts = 0
        booking.booking_otp_locked_until = None
        booking.booking_otp_verified_at = timezone.now()
        booking.start_service_pin = pin
        booking.start_pin_expiry = expiry
        booking.start_pin_attempts = 0
        booking.start_pin_locked_until = None
        booking.save()
        return pin

    @staticmethod
    def is_start_pin_locked(booking_id: int) -> bool:
        booking = Booking.objects.get(booking_id=booking_id)
        if booking.start_pin_locked_until and timezone.now() < booking.start_pin_locked_until:
            return True
        if booking.start_pin_locked_until and timezone.now() >= booking.start_pin_locked_until:
            booking.start_pin_locked_until = None
            booking.start_pin_attempts = 0
            booking.save()
        return False

    @staticmethod
    def record_start_pin_failure(booking_id: int, max_attempts: int = 5, lockout_minutes: int = 30) -> None:
        booking = Booking.objects.get(booking_id=booking_id)
        booking.start_pin_attempts += 1
        if booking.start_pin_attempts >= max_attempts:
            booking.start_pin_locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        booking.save()

    @staticmethod
    def start_service(booking_id: int, in_progress_status_id: int, booking_date, end_time, buffer_hours: int = 2) -> int:
        """Called only after the Start Service PIN has already been validated by the
        caller. Consumes the Start PIN (single-use) and mints the Completion PIN in the
        same write — mirrors confirm_arrival()'s eager-generation convention rather than
        generating it lazily on first customer read."""
        completion_pin = random.randint(1000, 9999)
        expiry = timezone.make_aware(datetime.combine(booking_date, end_time)) + timedelta(hours=buffer_hours)
        booking = Booking.objects.get(booking_id=booking_id)
        booking.status_id = in_progress_status_id
        booking.service_started_at = timezone.now()
        booking.start_service_pin = None
        booking.start_pin_expiry = None
        booking.start_pin_attempts = 0
        booking.start_pin_locked_until = None
        booking.completion_pin = completion_pin
        booking.completion_pin_expiry = expiry
        booking.completion_pin_attempts = 0
        booking.completion_pin_locked_until = None
        booking.save()
        return completion_pin

    @staticmethod
    def is_completion_pin_locked(booking_id: int) -> bool:
        booking = Booking.objects.get(booking_id=booking_id)
        if booking.completion_pin_locked_until and timezone.now() < booking.completion_pin_locked_until:
            return True
        if booking.completion_pin_locked_until and timezone.now() >= booking.completion_pin_locked_until:
            booking.completion_pin_locked_until = None
            booking.completion_pin_attempts = 0
            booking.save()
        return False

    @staticmethod
    def record_completion_pin_failure(booking_id: int, max_attempts: int = 5, lockout_minutes: int = 30) -> None:
        booking = Booking.objects.get(booking_id=booking_id)
        booking.completion_pin_attempts += 1
        if booking.completion_pin_attempts >= max_attempts:
            booking.completion_pin_locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        booking.save()

    @staticmethod
    def complete_service(booking_id: int, completed_status_id: int) -> None:
        """Called only after the Completion PIN has already been validated by the caller.
        Consumes the Completion PIN (single-use) in the same write as the status transition."""
        booking = Booking.objects.get(booking_id=booking_id)
        booking.status_id = completed_status_id
        booking.service_completed_at = timezone.now()
        booking.completion_pin = None
        booking.completion_pin_expiry = None
        booking.completion_pin_attempts = 0
        booking.completion_pin_locked_until = None
        booking.save()

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
        if cancelled_by is not None:
            # Booking is being rejected (pending) or cancelled (confirmed) — void every
            # verification credential issued for it so none can be replayed against a
            # dead booking, even though state checks elsewhere would already block it.
            booking.booking_otp = None
            booking.booking_otp_expiry = None
            booking.start_service_pin = None
            booking.start_pin_expiry = None
            booking.completion_pin = None
            booking.completion_pin_expiry = None
        booking.save()

    @staticmethod
    def mark_on_my_way(booking_id: int) -> None:
        Booking.objects.filter(booking_id=booking_id).update(
            on_my_way_at=timezone.now(), updated_at=timezone.now(),
        )
