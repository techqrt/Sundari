from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class PromoCode(models.Model):
    """A discount code an artist can apply to the registration fee. Created and managed in the Django admin.
    discount_percent is the only discount input: the amounts are always calculated on the server from the
    fee, never taken from a client. Codes are stored upper-case and matched case-insensitively."""

    promo_id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=40)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text='Percentage taken off the registration fee (1 to 100). 100 makes registration free.',
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_redemptions = models.PositiveIntegerField(
        null=True, blank=True, help_text='Overall limit across all artists. Empty means unlimited.',
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promo_codes'
        constraints = [
            models.UniqueConstraint(Lower('code'), name='unique_promo_code_case_insensitive'),
        ]

    def __str__(self):
        return f"{self.code} ({self.discount_percent}%)"

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        super().save(*args, **kwargs)


class PromoRedemption(models.Model):
    """One artist's use of a promo code on one registration payment. 'reserved' while the payment is open,
    'redeemed' once it completes, 'released' if it fails or is abandoned (the code is usable again). An
    artist can hold only one live (reserved or redeemed) redemption per code."""

    STATUS_CHOICES = [('reserved', 'Reserved'), ('redeemed', 'Redeemed'), ('released', 'Released')]

    redemption_id = models.AutoField(primary_key=True)
    promo = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name='redemptions')
    artist = models.ForeignKey('artists.ArtistProfile', on_delete=models.CASCADE, related_name='promo_redemptions')
    registration_payment = models.OneToOneField(
        'artists.ArtistRegistrationPayment', on_delete=models.CASCADE, related_name='redemption',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='reserved')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promo_redemptions'
        constraints = [
            models.UniqueConstraint(
                fields=['promo', 'artist'], condition=models.Q(status__in=['reserved', 'redeemed']),
                name='one_live_redemption_per_artist_per_promo',
            ),
        ]

    def __str__(self):
        return f"Redemption #{self.redemption_id} ({self.status})"
