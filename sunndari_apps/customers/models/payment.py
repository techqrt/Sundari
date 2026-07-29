import uuid
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    PAYMENT_TYPE_CHOICES = [('full', 'Full'), ('advance', 'Advance'), ('balance', 'Balance')]

    payment_id = models.AutoField(primary_key=True)
    booking = models.ForeignKey(
        'customers.Booking',
        on_delete=models.PROTECT,
        related_name='payments',
    )
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='payments_as_customer',
    )
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, default='full')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    artist_payout_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.ForeignKey(
        'core.PaymentStatus',
        on_delete=models.PROTECT,
        related_name='payments',
    )
    # gateway / gateway_order_id / gateway_payment_id stay null until a provider (Razorpay/PayU) is
    # confirmed and wired in — initiate_extract stubs an internal placeholder order id for now.
    gateway = models.CharField(max_length=20, null=True, blank=True)
    gateway_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    gateway_payment_id = models.CharField(max_length=100, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['booking']),
            models.Index(fields=['customer']),
        ]

    def __str__(self):
        return f"Payment #{self.payment_id} (Booking #{self.booking_id})"

    VALUES_FIELDS = (
        'payment_id', 'booking_id', 'customer_id', 'artist_id', 'payment_type',
        'amount', 'commission_amount', 'artist_payout_amount', 'status_id',
        'gateway', 'gateway_order_id', 'gateway_payment_id', 'paid_at',
        'failure_reason', 'created_at', 'updated_at',
    )

    def create(
        self,
        booking_id: int,
        customer_id: int,
        artist_id: int,
        amount,
        commission_amount,
        artist_payout_amount,
        status_id: int,
        payment_type: str = 'full',
    ) -> int:
        self.booking_id = booking_id
        self.customer_id = customer_id
        self.artist_id = artist_id
        self.payment_type = payment_type
        self.amount = amount
        self.commission_amount = commission_amount
        self.artist_payout_amount = artist_payout_amount
        self.status_id = status_id
        self.gateway_order_id = f'PENDING-{uuid.uuid4().hex[:16]}'
        self.save()
        return self.payment_id

    @staticmethod
    def get(payment_id: int) -> dict:
        return Payment.objects.filter(payment_id=payment_id).values(*Payment.VALUES_FIELDS).first()

    @staticmethod
    def get_by_gateway_order_id(gateway_order_id: str) -> dict:
        return Payment.objects.filter(gateway_order_id=gateway_order_id).values(*Payment.VALUES_FIELDS).first()

    @staticmethod
    def get_all(
        customer_id: int = None,
        artist_id: int = None,
        booking_id: int = None,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = Payment.objects.all()
        if customer_id:
            data = data.filter(customer_id=customer_id)
        if artist_id:
            data = data.filter(artist_id=artist_id)
        if booking_id:
            data = data.filter(booking_id=booking_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(gateway_order_id__icontains=search_key)
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*Payment.VALUES_FIELDS))

    @staticmethod
    def total_paid_for_booking(booking_id: int) -> float:
        total = Payment.objects.filter(
            booking_id=booking_id, status__name='paid',
        ).aggregate(models.Sum('amount'))['amount__sum']
        return total or 0

    @staticmethod
    def mark_paid(payment_id: int, gateway_payment_id: str, status_id: int) -> None:
        payment = Payment.objects.get(payment_id=payment_id)
        payment.gateway_payment_id = gateway_payment_id
        payment.status_id = status_id
        payment.paid_at = timezone.now()
        payment.save()

    @staticmethod
    def mark_failed(payment_id: int, status_id: int, failure_reason: str = None) -> None:
        payment = Payment.objects.get(payment_id=payment_id)
        payment.status_id = status_id
        payment.failure_reason = failure_reason
        payment.save()

    @staticmethod
    def mark_refunded(booking_id: int, status_id: int) -> None:
        # Full-refund stub: real cancellation policy (full vs partial vs none, based on
        # notice period) and the gateway refund API call both still need to be plugged in.
        Payment.objects.filter(booking_id=booking_id, status__name='paid').update(
            status_id=status_id, updated_at=timezone.now(),
        )
