from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class RedemptionTier(models.Model):
    tier_id = models.AutoField(primary_key=True)
    rupee_value = models.DecimalField(max_digits=10, decimal_places=2, unique=True)
    # Derived from rupee_value / CoinConfig.coin_value_rupees at save time (not
    # recomputed later) so a historical tier's coin cost stays stable even if the coin
    # value is subsequently changed by an admin.
    coin_cost = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'redemption_tiers'

    def __str__(self):
        return f"₹{self.rupee_value} = {self.coin_cost} coins"

    def _resolve_coin_cost(self) -> int:
        """Single source of truth for the rupee_value -> coin_cost conversion, shared by
        save() (raises ValueError, matching this codebase's convention for API/shell
        callers) and clean() (raises ValidationError, so the same rule shows up as a
        normal form error in Django Admin instead of a raw 500)."""
        from sunndari_apps.wallet.models.coin_config import CoinConfig

        # Field assignment doesn't coerce a raw str/float to Decimal until the DB write
        # itself — normalize here so the arithmetic below is always Decimal/Decimal,
        # never str/Decimal or float/Decimal.
        rupee_value = self.rupee_value if isinstance(self.rupee_value, Decimal) else Decimal(str(self.rupee_value))
        if rupee_value <= 0:
            # Without this, a non-positive value that happens to divide evenly (e.g.
            # -500.00) would sail through the check below and produce a negative
            # coin_cost, caught only by the DB's PositiveIntegerField CHECK constraint
            # — an unhandled IntegrityError instead of a clean error here.
            raise ValueError(f"₹{rupee_value} is not a valid redemption tier value — it must be a positive amount.")
        coin_value = CoinConfig.get_active().coin_value_rupees
        exact_coins = rupee_value / coin_value
        if exact_coins != exact_coins.to_integral_value():
            raise ValueError(
                f"₹{rupee_value} does not divide evenly by the current coin value (₹{coin_value})."
            )
        return int(exact_coins)

    def clean(self):
        if self.rupee_value is None:
            return
        try:
            self._resolve_coin_cost()
        except ValueError as e:
            raise ValidationError({'rupee_value': str(e)})

    def save(self, *args, **kwargs):
        self.coin_cost = self._resolve_coin_cost()
        super().save(*args, **kwargs)

    @staticmethod
    def get_all_active() -> list:
        return list(
            RedemptionTier.objects.filter(is_active=True).order_by('rupee_value').values(
                'tier_id', 'rupee_value', 'coin_cost', 'is_active',
            )
        )
