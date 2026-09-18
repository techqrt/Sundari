from celery import shared_task
from django.db import transaction
from django.utils import timezone
from sunndari_apps.wallet.models.coin_transaction import CoinTransaction
from sunndari_apps.wallet.models.customer_wallet import CustomerWallet


@shared_task
def expire_lapsed_coins() -> int:
    """Runs periodically (see CELERY_BEAT_SCHEDULE). CustomerWallet.debit() already
    refuses to spend a batch past its expires_at even before this runs (its post-loop
    consistency guard treats "no unexpired batch left to draw from" as insufficient
    balance) — but nothing else ever decrements balance_coins or records that the coins
    are gone. Without this task, a customer's visible balance would stay permanently
    inflated by coins they can no longer actually spend. This is what performs that
    write: for every CASHBACK/REVERSAL batch whose expires_at has passed with
    remaining_coins still > 0, zero the batch, decrement the wallet, and log an EXPIRY
    entry pointing back at the batch that lapsed.

    Lock order is wallet-then-batch throughout, matching CustomerWallet.debit() (which
    locks the wallet, then the batches it draws from) — reversing that order here would
    risk a deadlock against a debit() running concurrently on the same wallet.
    """
    lapsed = list(
        CoinTransaction.objects.filter(
            transaction_type__in=CoinTransaction.BATCH_TRANSACTION_TYPES,
            remaining_coins__gt=0,
            expires_at__lte=timezone.now(),
        ).values_list('transaction_id', 'wallet_id')
    )

    expired_count = 0
    for transaction_id, wallet_id in lapsed:
        with transaction.atomic():
            wallet = CustomerWallet.objects.select_for_update().get(customer_id=wallet_id)
            batch = CoinTransaction.objects.select_for_update().get(transaction_id=transaction_id)
            # Re-check under lock — a concurrent debit() may have already fully drawn
            # down this batch (or another run of this same task already swept it)
            # between the unlocked scan above and acquiring the lock here.
            if batch.remaining_coins <= 0 or batch.expires_at is None or batch.expires_at > timezone.now():
                continue

            expiring_coins = batch.remaining_coins
            batch.remaining_coins = 0
            batch.save(update_fields=['remaining_coins'])
            wallet.balance_coins -= expiring_coins
            wallet.save()
            CoinTransaction.objects.create(
                wallet=wallet,
                booking_id=batch.booking_id,
                transaction_type='EXPIRY',
                coins=-expiring_coins,
                balance_after=wallet.balance_coins,
                reference_transaction=batch,
            )
        expired_count += 1
    return expired_count
