from datetime import timedelta
from decimal import Decimal, ROUND_FLOOR
from django.db import models, transaction
from django.utils import timezone


class CustomerWallet(models.Model):
    customer = models.OneToOneField(
        'authentication.User',
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='wallet',
    )
    balance_coins = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_wallets'

    def __str__(self):
        return f"Wallet (Customer #{self.customer_id}) — {self.balance_coins} coins"

    @staticmethod
    def get(customer_id: int) -> dict:
        return CustomerWallet.objects.filter(customer_id=customer_id).values(
            'customer_id', 'balance_coins', 'created_at', 'updated_at',
        ).first()

    @staticmethod
    def get_or_create_for_customer(customer_id: int) -> 'CustomerWallet':
        wallet, _ = CustomerWallet.objects.get_or_create(customer_id=customer_id)
        return wallet

    @staticmethod
    def credit(
        customer_id: int,
        coins: int,
        transaction_type: str,
        booking_id: int = None,
        expiry_days: int = None,
        rupee_equivalent=None,
    ) -> 'CoinTransaction':
        """Atomically increases the wallet balance and writes the matching ledger row.
        For a BATCH_TRANSACTION_TYPES type (CASHBACK/REVERSAL), the new row also becomes
        a FIFO-consumable, independently-expiring batch (remaining_coins=coins,
        expires_at=now+expiry_days, falling back to CoinConfig's configured value)."""
        from sunndari_apps.wallet.models.coin_transaction import CoinTransaction
        from sunndari_apps.wallet.models.coin_config import CoinConfig

        if coins <= 0:
            raise ValueError('Credit amount must be a positive number of coins.')

        with transaction.atomic():
            CustomerWallet.objects.get_or_create(customer_id=customer_id)
            wallet = CustomerWallet.objects.select_for_update().get(customer_id=customer_id)
            wallet.balance_coins += coins
            wallet.save()

            remaining_coins = None
            expires_at = None
            if transaction_type in CoinTransaction.BATCH_TRANSACTION_TYPES:
                remaining_coins = coins
                days = expiry_days if expiry_days is not None else CoinConfig.get_active().coin_expiry_days
                expires_at = timezone.now() + timedelta(days=days)

            return CoinTransaction.objects.create(
                wallet=wallet,
                booking_id=booking_id,
                transaction_type=transaction_type,
                coins=coins,
                balance_after=wallet.balance_coins,
                remaining_coins=remaining_coins,
                expires_at=expires_at,
                rupee_equivalent=rupee_equivalent,
            )

    @staticmethod
    def debit(
        customer_id: int,
        coins: int,
        transaction_type: str,
        booking_id: int = None,
        payment_id: int = None,
        rupee_equivalent=None,
    ) -> 'CoinTransaction':
        """Atomically decreases the wallet balance, drawing down unexpired
        BATCH_TRANSACTION_TYPES batches FIFO (oldest first) so remaining_coins stays
        accurate for the expiry sweep, then writes the matching ledger row. Raises
        ValueError on insufficient balance — this check happens under the same lock
        used to apply the debit, so it is the authoritative guard against a race
        between two concurrent redemption requests, not just an earlier best-effort
        check by the caller."""
        from sunndari_apps.wallet.models.coin_transaction import CoinTransaction

        if coins <= 0:
            raise ValueError('Debit amount must be a positive number of coins.')

        with transaction.atomic():
            CustomerWallet.objects.get_or_create(customer_id=customer_id)
            wallet = CustomerWallet.objects.select_for_update().get(customer_id=customer_id)
            if wallet.balance_coins < coins:
                raise ValueError('Insufficient coin balance.')

            remaining_to_consume = coins
            batches = CoinTransaction.objects.select_for_update().filter(
                wallet=wallet,
                transaction_type__in=CoinTransaction.BATCH_TRANSACTION_TYPES,
                remaining_coins__gt=0,
                expires_at__gt=timezone.now(),
            ).order_by('created_at')
            for batch in batches:
                if remaining_to_consume <= 0:
                    break
                consumed = min(batch.remaining_coins, remaining_to_consume)
                batch.remaining_coins -= consumed
                batch.save(update_fields=['remaining_coins'])
                remaining_to_consume -= consumed

            if remaining_to_consume > 0:
                # balance_coins said there was enough, but the unexpired batches backing
                # it don't cover the request — some coins counted toward balance_coins
                # have passed their expiry and the periodic sweep just hasn't caught up
                # yet. Roll back (any batch decrements above are undone with this raise)
                # rather than let the debit proceed against coins that are effectively
                # already expired.
                raise ValueError('Insufficient coin balance.')

            wallet.balance_coins -= coins
            wallet.save()

            return CoinTransaction.objects.create(
                wallet=wallet,
                booking_id=booking_id,
                payment_id=payment_id,
                transaction_type=transaction_type,
                coins=-coins,
                balance_after=wallet.balance_coins,
                rupee_equivalent=rupee_equivalent,
            )

    @staticmethod
    def award_cashback(customer_id: int, booking_id: int, service_amount) -> 'CoinTransaction':
        """₹→coins conversion for cashback, kept in one place rather than duplicated at
        every call site: cashback_percentage of service_amount, converted to coins at
        the current coin value, floored to a whole coin (rounds in the platform's
        favor rather than inventing a round-up policy that would silently overpay on
        every booking). Returns None without crediting anything if that rounds down to
        zero coins — e.g. an unexpectedly tiny service_amount — rather than raising
        through CustomerWallet.credit()'s positive-amount guard."""
        from sunndari_apps.wallet.models.coin_config import CoinConfig

        config = CoinConfig.get_active()
        cashback_rupees = (Decimal(service_amount) * config.cashback_percentage) / Decimal('100')
        cashback_coins = int((cashback_rupees / config.coin_value_rupees).to_integral_value(rounding=ROUND_FLOOR))
        if cashback_coins <= 0:
            return None

        return CustomerWallet.credit(
            customer_id=customer_id,
            coins=cashback_coins,
            transaction_type='CASHBACK',
            booking_id=booking_id,
        )

    @staticmethod
    def reverse_redemption(redemption_transaction_id: int) -> 'CoinTransaction':
        """Credits back the coins from a specific REDEMPTION — used when a booking whose
        payment included a coin redemption is cancelled and that payment is fully
        refunded. Grants a fresh batch with its own new expiry window rather than
        restoring the original (possibly partially-elapsed) CASHBACK batches that were
        consumed — simpler, and only errs in the customer's favor. Refuses to reverse
        the same redemption twice."""
        from sunndari_apps.wallet.models.coin_transaction import CoinTransaction

        with transaction.atomic():
            redemption = CoinTransaction.objects.select_for_update().get(
                transaction_id=redemption_transaction_id, transaction_type='REDEMPTION',
            )
            already_reversed = CoinTransaction.objects.filter(
                transaction_type='REVERSAL', reference_transaction_id=redemption_transaction_id,
            ).exists()
            if already_reversed:
                raise ValueError('This redemption has already been reversed.')

            credited = CustomerWallet.credit(
                customer_id=redemption.wallet.customer_id,
                coins=abs(redemption.coins),
                transaction_type='REVERSAL',
                booking_id=redemption.booking_id,
                rupee_equivalent=redemption.rupee_equivalent,
            )
            credited.reference_transaction_id = redemption_transaction_id
            credited.save(update_fields=['reference_transaction_id'])
            return credited

    @staticmethod
    def reverse_all_redemptions_for_booking(booking_id: int) -> int:
        """Reverses every un-reversed REDEMPTION tied to a booking — the common step
        behind every path that cancels a booking (customer-initiated, artist-initiated,
        and the auto-expiry sweep for stale pending bookings), since a redemption can
        happen at /initiate/ time even if that specific payment attempt never actually
        completed. Returns how many were reversed."""
        from sunndari_apps.wallet.models.coin_transaction import CoinTransaction

        unreversed_redemptions = CoinTransaction.objects.filter(
            booking_id=booking_id, transaction_type='REDEMPTION', reversals__isnull=True,
        )
        count = 0
        for redemption in unreversed_redemptions:
            CustomerWallet.reverse_redemption(redemption_transaction_id=redemption.transaction_id)
            count += 1
        return count
