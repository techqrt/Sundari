from django.db import models
from django.db.models import Q
from django.utils import timezone


class CoinTransaction(models.Model):
    # No REFUND type: cancellation reverses a specific REDEMPTION (see REVERSAL,
    # reference_transaction below) rather than modeling a separate refund concept.
    TRANSACTION_TYPE_CHOICES = [
        ('CASHBACK', 'Cashback'),
        ('REDEMPTION', 'Redemption'),
        ('REVERSAL', 'Reversal'),
        ('EXPIRY', 'Expiry'),
        ('ADJUSTMENT', 'Adjustment'),
    ]

    # Every *credit* type is tracked as an independently-expiring, FIFO-consumable
    # "batch" (remaining_coins + expires_at get populated for these, and
    # CustomerWallet.debit() only draws down batches of these types) — a coin that
    # increases balance_coins but isn't in a batch could never actually be spent, since
    # debit() only draws from batches. CASHBACK is the obvious case; REVERSAL also gets
    # a fresh batch/expiry so coins returned when a redeemed booking is cancelled don't
    # become permanently un-expiring; ADJUSTMENT (an admin manually crediting coins)
    # needs the same treatment for the same reason — it's still spendable balance.
    # REDEMPTION and EXPIRY are always debits, never batches.
    BATCH_TRANSACTION_TYPES = ('CASHBACK', 'REVERSAL', 'ADJUSTMENT')

    transaction_id = models.AutoField(primary_key=True)
    wallet = models.ForeignKey(
        'wallet.CustomerWallet',
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    booking = models.ForeignKey(
        'customers.Booking',
        on_delete=models.PROTECT,
        related_name='coin_transactions',
        null=True,
        blank=True,
    )
    # Set on REDEMPTION rows only — the specific Payment this redemption was applied
    # to. Needed to determine whether the redeemed value should count toward a
    # booking's settled total (see Payment.total_settled_for_booking): a booking can
    # have multiple payment attempts (a failed one, then a successful retry), so
    # `booking` alone can't tell which attempt a given redemption belongs to, or
    # whether that attempt actually succeeded.
    payment = models.ForeignKey(
        'payments.Payment',
        on_delete=models.PROTECT,
        related_name='coin_transactions',
        null=True,
        blank=True,
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    coins = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    # Only set on CASHBACK rows — tracks unspent coins from this specific batch so
    # redemption/expiry can consume batches FIFO (oldest first) without touching others.
    remaining_coins = models.PositiveIntegerField(null=True, blank=True)
    # Only set on CASHBACK rows — this batch's own 1-year expiry, independent of any
    # other batch's expiry.
    expires_at = models.DateTimeField(null=True, blank=True)
    # Set on REDEMPTION/REVERSAL rows — the ₹ value of the tier involved, kept here so
    # the audit trail survives even if the RedemptionTier is later edited or deleted.
    rupee_equivalent = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Set on REVERSAL rows (points back at the REDEMPTION it undoes) and on EXPIRY rows
    # (points back at the CASHBACK/REVERSAL batch that lapsed) — whichever prior
    # transaction this row's coin movement is "about".
    reference_transaction = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversals',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'coin_transactions'
        indexes = [
            models.Index(fields=['wallet']),
            models.Index(fields=['booking']),
        ]
        constraints = [
            # Defense-in-depth backstop for the row-lock fix in
            # verify_completion_pin_extract: even if some other, currently-nonexistent
            # code path ever awarded cashback without going through that lock, the
            # database itself refuses a second CASHBACK row for the same booking.
            models.UniqueConstraint(
                fields=['booking'],
                condition=Q(transaction_type='CASHBACK'),
                name='unique_cashback_per_booking',
            ),
        ]

    def __str__(self):
        return f"CoinTransaction #{self.transaction_id} ({self.transaction_type} {self.coins})"

    VALUES_FIELDS = (
        'transaction_id', 'wallet_id', 'booking_id', 'payment_id', 'transaction_type',
        'coins', 'balance_after', 'remaining_coins', 'expires_at', 'rupee_equivalent',
        'reference_transaction_id', 'created_at',
    )

    @staticmethod
    def get_all(
        wallet_id: int = None,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = CoinTransaction.objects.all()
        if wallet_id:
            data = data.filter(wallet_id=wallet_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(transaction_type__icontains=search_key)
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*CoinTransaction.VALUES_FIELDS))
