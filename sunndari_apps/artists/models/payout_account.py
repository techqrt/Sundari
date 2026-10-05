from django.db import models
from django.utils import timezone

from sunndari_apps.common.crypto import encrypt_text, decrypt_text


class ArtistPayoutAccount(models.Model):
    payout_account_id = models.AutoField(primary_key=True)
    artist = models.OneToOneField(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='payout_account',
    )
    account_holder_name = models.CharField(max_length=200)
    # Stored encrypted (Fernet token) — read it only through ArtistPayoutAccount.get().
    bank_account_number = models.CharField(max_length=255)
    ifsc_code = models.CharField(max_length=11)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    verification_status = models.ForeignKey(
        'core.ApprovalStatus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_payout_accounts'

    def __str__(self):
        return f"Payout account (Artist #{self.artist_id})"

    @staticmethod
    def set_for_artist(
        artist_id: int,
        account_holder_name: str,
        bank_account_number: str,
        ifsc_code: str,
        upi_id: str = None,
    ) -> int:
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        pending = ApprovalStatus.objects.filter(name='pending').first()
        obj, created = ArtistPayoutAccount.objects.update_or_create(
            artist_id=artist_id,
            defaults={
                'account_holder_name': account_holder_name,
                'bank_account_number': encrypt_text(bank_account_number),
                'ifsc_code': ifsc_code,
                'upi_id': upi_id,
                'verification_status': pending,
            },
        )
        return obj.payout_account_id

    @staticmethod
    def get(artist_id: int) -> dict:
        row = ArtistPayoutAccount.objects.filter(artist_id=artist_id).values(
            'payout_account_id', 'artist_id', 'account_holder_name', 'bank_account_number',
            'ifsc_code', 'upi_id', 'verification_status_id', 'created_at', 'updated_at',
        ).first()
        if row:
            row['bank_account_number'] = decrypt_text(row['bank_account_number']) or ''
        return row
