from django.db import models
from django.utils import timezone


class ArtistRegistrationPayment(models.Model):
    """The one-time registration fee an artist pays before submitting their profile for review. Kept apart
    from payments.Payment (which belongs to a booking) so the booking payment flow is untouched. The fee,
    discount and payable amount are saved as they were calculated on the server at initiate time."""

    registration_payment_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile', on_delete=models.CASCADE, related_name='registration_payments',
    )
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payable_amount = models.DecimalField(max_digits=10, decimal_places=2)
    promo = models.ForeignKey(
        'artists.PromoCode', on_delete=models.PROTECT, null=True, blank=True, related_name='registration_payments',
    )
    status = models.ForeignKey(
        'core.PaymentStatus', on_delete=models.PROTECT, related_name='registration_payments',
    )
    # 'razorpay' for a gateway payment, 'promo' when a 100% code made the payable amount zero.
    gateway = models.CharField(max_length=20, null=True, blank=True)
    gateway_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    gateway_payment_id = models.CharField(max_length=100, null=True, blank=True)
    # Set when the payment completes and kept as the record afterwards. A completed payment that has since been
    # voided (refund_requested_at set, e.g. the artist was rejected) no longer counts; an artist can have at
    # most one completed, un-voided row.
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=300, null=True, blank=True)
    # Refund ledger, same idea as payments.Payment: refund_requested_at is set the moment money is owed back
    # (a capture that could not be applied, or a rejected artist); gateway_refund_id is set once the gateway
    # has accepted the refund, which ends the obligation.
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refund_attempts = models.PositiveSmallIntegerField(default=0)
    refund_last_attempt_at = models.DateTimeField(null=True, blank=True)
    gateway_refund_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_registration_payments'
        indexes = [models.Index(fields=['artist', '-created_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['artist'], condition=models.Q(paid_at__isnull=False, refund_requested_at__isnull=True),
                name='one_completed_registration_payment_per_artist',
            ),
        ]

    def __str__(self):
        return f"Registration payment #{self.registration_payment_id} (Artist #{self.artist_id})"
