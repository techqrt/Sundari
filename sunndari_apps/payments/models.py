import logging
import uuid
from django.db import models, transaction
from django.utils import timezone

from sunndari_apps.payments.gateway import RazorpayGateway

logger = logging.getLogger(__name__)


class PaymentOrder(models.Model):
    """Groups multiple bookings' Payment rows under a single gateway checkout — e.g. a
    customer paying for several bookings created via one multi-quantity flow gets one
    Razorpay order for the combined total, rather than a separate charge per booking.
    Individual Payment rows keep their own booking_id/artist_id/commission/payout
    exactly as they do for a solo payment; this model exists purely to reconcile the
    one shared gateway transaction back to all of them together at verify time."""

    order_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='payment_orders',
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.ForeignKey(
        'core.PaymentStatus',
        on_delete=models.PROTECT,
        related_name='payment_orders',
    )
    gateway = models.CharField(max_length=20, null=True, blank=True)
    gateway_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    gateway_payment_id = models.CharField(max_length=100, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payment_orders'
        indexes = [
            models.Index(fields=['customer']),
        ]

    def __str__(self):
        return f"PaymentOrder #{self.order_id} (Customer #{self.customer_id})"

    VALUES_FIELDS = (
        'order_id', 'customer_id', 'total_amount', 'status_id',
        'gateway', 'gateway_order_id', 'gateway_payment_id', 'paid_at',
        'failure_reason', 'created_at', 'updated_at',
    )

    def create(self, customer_id: int, total_amount, status_id: int) -> int:
        self.customer_id = customer_id
        self.total_amount = total_amount
        self.status_id = status_id
        self.gateway_order_id = f'PENDING-{uuid.uuid4().hex[:16]}'
        self.save()
        return self.order_id

    @staticmethod
    def get(order_id: int) -> dict:
        return PaymentOrder.objects.filter(order_id=order_id).values(*PaymentOrder.VALUES_FIELDS).first()

    @staticmethod
    def get_by_gateway_order_id(gateway_order_id: str) -> dict:
        return PaymentOrder.objects.filter(
            gateway_order_id=gateway_order_id,
        ).values(*PaymentOrder.VALUES_FIELDS).first()

    @staticmethod
    def set_gateway_order(order_id: int, gateway: str, gateway_order_id: str) -> None:
        """Replaces the placeholder order id set at create() time with the real
        gateway-issued order id, once the gateway call actually succeeds — mirrors
        Payment.set_gateway_order for the same reason."""
        order = PaymentOrder.objects.get(order_id=order_id)
        order.gateway = gateway
        order.gateway_order_id = gateway_order_id
        order.save()

    @staticmethod
    def mark_paid(order_id: int, gateway_payment_id: str, status_id: int) -> None:
        """Marks the order AND every Payment row under it paid together — a group
        checkout is all-or-nothing from the customer's perspective, so its Payments
        must always move in lockstep with the order itself, never independently."""
        with transaction.atomic():
            order = PaymentOrder.objects.select_for_update().get(order_id=order_id)
            order.gateway_payment_id = gateway_payment_id
            order.status_id = status_id
            order.paid_at = timezone.now()
            order.failure_reason = None
            order.save()
            Payment.objects.filter(order_id=order_id).update(
                gateway_payment_id=gateway_payment_id, status_id=status_id,
                paid_at=order.paid_at, failure_reason=None, updated_at=timezone.now(),
            )

    @staticmethod
    def mark_paid_checked(order_id: int, gateway_payment_id: str, status_id: int) -> bool:
        """mark_paid() for a group order, refusing (and changing nothing) if any booking in it
        would be pushed past its total by the payment it carries."""
        from sunndari_apps.customers.models.booking import Booking
        with transaction.atomic():
            for payment in Payment.objects.select_for_update().filter(order_id=order_id):
                booking = Booking.objects.select_for_update().get(booking_id=payment.booking_id)
                if Payment.total_settled_for_booking(payment.booking_id) + payment.amount > booking.total_amount:
                    return False
            PaymentOrder.mark_paid(order_id=order_id, gateway_payment_id=gateway_payment_id, status_id=status_id)
            return True

    @staticmethod
    def mark_failed(order_id: int, status_id: int, failure_reason: str = None) -> None:
        with transaction.atomic():
            order = PaymentOrder.objects.select_for_update().get(order_id=order_id)
            order.status_id = status_id
            order.failure_reason = failure_reason
            order.save()
            Payment.objects.filter(order_id=order_id).update(
                status_id=status_id, failure_reason=failure_reason, updated_at=timezone.now(),
            )


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
    # Only set for a payment created via /payments/initiate_group/ — groups this
    # booking's own Payment row together with the other bookings paid in the same
    # checkout, so /verify/ can reconcile one shared gateway transaction back to all
    # of them. A solo /initiate/ payment leaves this null, unchanged from before.
    order = models.ForeignKey(
        'payments.PaymentOrder',
        on_delete=models.PROTECT,
        related_name='payments',
        null=True,
        blank=True,
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
    # Refund ledger. refund_requested_at is set the moment money is owed back to the customer (a cancelled
    # booking, or a gateway capture that could not be applied); gateway_refund_id is set once the gateway
    # has accepted the refund, which is what ends the obligation. Attempts and the last attempt time drive
    # the exponential backoff of the retry job.
    refund_requested_at = models.DateTimeField(null=True, blank=True)
    refund_attempts = models.PositiveSmallIntegerField(default=0)
    refund_last_attempt_at = models.DateTimeField(null=True, blank=True)
    gateway_refund_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        indexes = [
            models.Index(fields=['booking']),
            models.Index(fields=['customer']),
            models.Index(fields=['order']),
        ]

    def __str__(self):
        return f"Payment #{self.payment_id} (Booking #{self.booking_id})"

    VALUES_FIELDS = (
        'payment_id', 'booking_id', 'customer_id', 'artist_id', 'order_id', 'payment_type',
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
        order_id: int = None,
    ) -> int:
        self.booking_id = booking_id
        self.customer_id = customer_id
        self.artist_id = artist_id
        self.order_id = order_id
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
    def total_settled_for_booking(booking_id: int):
        """Total value applied toward a booking's total_amount — cash actually paid
        PLUS the rupee value of any coin redemption tied to a payment that actually
        succeeded. A booking's total_amount is denominated in rupees regardless of
        whether the customer covered part of it with cash or with redeemed coins, so
        both must count when deciding whether a booking has been fully settled (e.g.
        before the artist can confirm it, or when computing how much is still owed) —
        total_paid_for_booking() alone only reflects what was charged via the gateway,
        which understates this whenever redemption was used. Filters on
        payment__status__name='paid' (not just "not reversed") so a redemption tied to
        a payment that was never completed, or whose booking was later cancelled and
        refunded, never counts as settled."""
        from sunndari_apps.wallet.models.coin_transaction import CoinTransaction

        cash_paid = Payment.total_paid_for_booking(booking_id=booking_id)
        redeemed_value = CoinTransaction.objects.filter(
            transaction_type='REDEMPTION',
            payment__booking_id=booking_id,
            payment__status__name='paid',
        ).aggregate(models.Sum('rupee_equivalent'))['rupee_equivalent__sum'] or 0
        return cash_paid + redeemed_value

    @staticmethod
    def set_gateway_order(payment_id: int, gateway: str, gateway_order_id: str) -> None:
        """Replaces the placeholder order id set at create() time with the real
        gateway-issued order id, once the gateway call actually succeeds."""
        payment = Payment.objects.get(payment_id=payment_id)
        payment.gateway = gateway
        payment.gateway_order_id = gateway_order_id
        payment.save()

    @staticmethod
    def mark_paid(payment_id: int, gateway_payment_id: str, status_id: int) -> None:
        payment = Payment.objects.get(payment_id=payment_id)
        payment.gateway_payment_id = gateway_payment_id
        payment.status_id = status_id
        payment.paid_at = timezone.now()
        # A prior failed attempt on this same row (e.g. a bad first /verify/ call
        # followed by a successful retry) must not leave a stale failure_reason
        # sitting alongside a now-successful payment in the transaction history.
        payment.failure_reason = None
        payment.save()

    @staticmethod
    def mark_paid_checked(payment_id: int, gateway_payment_id: str, status_id: int) -> bool:
        """mark_paid(), but only if the booking is not pushed past its total by this payment.
        The booking row is locked for the check so two payments verified at the same moment
        cannot both pass it. Returns False (and changes nothing) when it would overpay."""
        from sunndari_apps.customers.models.booking import Booking
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(payment_id=payment_id)
            booking = Booking.objects.select_for_update().get(booking_id=payment.booking_id)
            if Payment.total_settled_for_booking(payment.booking_id) + payment.amount > booking.total_amount:
                return False
            Payment.mark_paid(payment_id=payment_id, gateway_payment_id=gateway_payment_id, status_id=status_id)
            return True

    @staticmethod
    def mark_paid_via_wallet(payment_id: int, status_id: int) -> None:
        """For a payment fully covered by redeemed coins — no Razorpay order was ever
        created (a ₹0 order would be rejected by the gateway outright), so this clears
        the create()-time 'PENDING-xxxx' placeholder gateway_order_id rather than
        leaving it sitting alongside a 'paid' status, and marks gateway='wallet' so
        how the payment was actually settled stays visible/auditable."""
        payment = Payment.objects.get(payment_id=payment_id)
        payment.gateway = 'wallet'
        payment.gateway_order_id = None
        payment.status_id = status_id
        payment.paid_at = timezone.now()
        payment.failure_reason = None
        payment.save()

    @staticmethod
    def mark_failed(payment_id: int, status_id: int, failure_reason: str = None) -> None:
        payment = Payment.objects.get(payment_id=payment_id)
        payment.status_id = status_id
        payment.failure_reason = failure_reason
        payment.save()

    @staticmethod
    def mark_unapplied_capture(payment_id: int, gateway_payment_id: str, status_id: int, failure_reason: str) -> None:
        """The gateway captured this payment but it cannot be applied to its booking (the booking is no
        longer active, or it would overpay it). The money is the customer's, so it is recorded as
        failed-with-a-refund-owed rather than kept: the gateway payment id is stored so the refund can be
        made and retried, and refund_requested_at marks the obligation."""
        now = timezone.now()
        Payment.objects.filter(payment_id=payment_id).update(
            gateway_payment_id=gateway_payment_id, status_id=status_id, failure_reason=failure_reason[:300],
            refund_requested_at=now, updated_at=now,
        )

    @staticmethod
    def _already_refunded_at_gateway(payment: 'Payment', paise: int) -> bool:
        """After a refund call fails, its outcome is unknown: the gateway may have accepted the refund and
        only the reply was lost. Ask it, so a lost reply is never reported as a failure (and never retried
        into a second refund). A group payment shares one gateway payment, so only a fully refunded one
        counts there."""
        try:
            fetched = RazorpayGateway.get_client().payment.fetch(payment.gateway_payment_id)
        except Exception:
            return False
        if not isinstance(fetched, dict):
            return False
        if fetched.get('status') == 'refunded':
            return True
        refunded = fetched.get('amount_refunded')
        return payment.order_id is None and isinstance(refunded, int) and refunded >= paise

    @staticmethod
    def _refund_at_gateway(payment: 'Payment') -> str:
        """Asks the gateway to return the cash part of one payment. Returns '' on success or a
        short reason on failure. Wallet-only or zero-cash payments have nothing to return."""
        if payment.gateway == 'wallet' or not payment.gateway_payment_id or payment.amount <= 0:
            return ''
        paise = int(round(payment.amount * 100))
        try:
            refund = RazorpayGateway.get_client().payment.refund(payment.gateway_payment_id, {
                'amount': paise,
                'notes': {'payment_id': str(payment.payment_id), 'booking_id': str(payment.booking_id)},
            })
            refund_id = refund.get('id') if isinstance(refund, dict) else None
            if isinstance(refund_id, str):
                Payment.objects.filter(payment_id=payment.payment_id).update(gateway_refund_id=refund_id)
            return ''
        except Exception as error:                      # network, auth, already-refunded, over-refund ...
            logger.exception('Gateway refund failed for payment %s', payment.payment_id)
            if Payment._already_refunded_at_gateway(payment, paise):
                return ''
            return f'Refund failed: {str(error)[:200]}'

    @staticmethod
    def refund_payment(payment: 'Payment', refunded_status_id: int) -> bool:
        """One refund attempt for one payment, with the bookkeeping the retry job relies on. A payment
        only becomes 'refunded' once the gateway has accepted the refund; if the call fails it keeps its
        status with the reason and attempt count recorded (the customer is told once), so the system never
        claims money was returned when it was not."""
        from sunndari_apps.notifications.utils import NotificationService
        now = timezone.now()
        problem = Payment._refund_at_gateway(payment)
        if problem:
            Payment.objects.filter(payment_id=payment.payment_id).update(
                failure_reason=problem, refund_requested_at=payment.refund_requested_at or now,
                refund_attempts=models.F('refund_attempts') + 1, refund_last_attempt_at=now, updated_at=now,
            )
            if payment.refund_attempts == 0:
                NotificationService.notify(
                    user_id=payment.customer_id, title='Refund being processed',
                    message='We could not return your payment automatically yet. Our team will complete the refund.',
                    type='refund_pending', booking_id=payment.booking_id,
                )
            return False
        # A captured-but-unapplied payment keeps its reason as the audit trail of why it was refunded.
        keep_reason = payment.status.name != 'paid'
        Payment.objects.filter(payment_id=payment.payment_id).update(
            status_id=refunded_status_id, failure_reason=payment.failure_reason if keep_reason else None,
            refund_requested_at=payment.refund_requested_at or now, refund_last_attempt_at=now, updated_at=now,
        )
        if payment.amount > 0:
            NotificationService.notify(
                user_id=payment.customer_id, title='Refund initiated',
                message=f'A refund of ₹{payment.amount} has been initiated to your original payment method.',
                type='refund_initiated', booking_id=payment.booking_id,
            )
        return True

    @staticmethod
    def mark_refunded(booking_id: int, status_id: int) -> dict:
        """Refunds every paid payment of a booking (see refund_payment). Failures are picked up again by
        the retry_owed_refunds job."""
        outcome = {'refunded': 0, 'pending': 0}
        for payment in Payment.objects.select_related('status').filter(booking_id=booking_id, status__name='paid'):
            outcome['refunded' if Payment.refund_payment(payment, status_id) else 'pending'] += 1
        return outcome

    @staticmethod
    def retry_owed_refunds(force: bool = False) -> dict:
        """Settles every refund still owed: paid payments of cancelled / missed bookings, and captures that
        could not be applied. Each payment is retried with exponential backoff (base * 2^attempts, capped)
        and, once the attempts are used up, escalated to the admins exactly once instead of retried
        forever. `force` ignores the backoff and the cap (the manual `retry_refunds` command)."""
        from django.db.models import Q
        from sunndari_apps.authentication.models import User
        from sunndari_apps.core.models.payment_status import PaymentStatus
        from sunndari_apps.notifications.models.notification import Notification
        from sunndari_apps.notifications.utils import NotificationService
        from sunndari.config import Configurations

        refunded_status = PaymentStatus.objects.get(name='refunded')
        now = timezone.now()
        owed = Payment.objects.select_related('status').filter(gateway_refund_id__isnull=True).filter(
            Q(status__name='paid', booking__status__name__in=['cancelled', 'no_show'])
            | Q(status__name='failed', refund_requested_at__isnull=False, gateway_payment_id__isnull=False)
        )
        outcome = {'refunded': 0, 'pending': 0, 'waiting': 0, 'escalated': 0}
        for payment in owed:
            if not force and payment.refund_attempts >= Configurations.refund_max_attempts:
                outcome['escalated'] += 1
                title = 'Refund needs manual attention'
                for admin_id in User.objects.filter(role='admin', is_active=True).values_list('user_id', flat=True):
                    if not Notification.objects.filter(user_id=admin_id, booking_id=payment.booking_id, title=title).exists():
                        NotificationService.notify(
                            user_id=admin_id, title=title, type='payment_status', booking_id=payment.booking_id,
                            message=f'Payment #{payment.payment_id} (₹{payment.amount}) could not be refunded after '
                                    f'{payment.refund_attempts} attempts: {payment.failure_reason}',
                        )
                continue
            if not force and payment.refund_last_attempt_at:
                wait = min(Configurations.refund_backoff_base_seconds * 2 ** payment.refund_attempts,
                           Configurations.refund_backoff_max_seconds)
                if now < payment.refund_last_attempt_at + timezone.timedelta(seconds=wait):
                    outcome['waiting'] += 1
                    continue
            outcome['refunded' if Payment.refund_payment(payment, refunded_status.status_id) else 'pending'] += 1
        return outcome
