from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


class CoinConfig(models.Model):
    """Singleton settings row (always pk=1) — admin-editable equivalents of what would
    otherwise be hardcoded Configurations constants, since these must change without a
    deploy. save() pins the pk so there can never be more than one row."""

    config_id = models.AutoField(primary_key=True)
    # Decimal literals, never bare floats — a float default here would carry the same
    # floating-point imprecision this project avoids everywhere else for money/coins.
    cashback_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('10.00'),
        validators=[MinValueValidator(Decimal('0'))],
        # The name is kept so existing rows, admin links and API consumers keep working, but the
        # value is paise of cashback per ₹100 of service amount (10 → ₹2 on a ₹2000 booking).
        verbose_name='Cashback (paise per ₹100)',
        help_text='Paise of cashback earned per ₹100 of service amount. 10 means ₹2 on a ₹2000 booking.',
    )
    # Floored above zero, not just non-negative — award_cashback() and
    # RedemptionTier.save() both divide by this value, so an admin-entered 0 would
    # otherwise raise ZeroDivisionError the next time either runs.
    coin_value_rupees = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('0.01'),
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    coin_expiry_days = models.PositiveIntegerField(default=365)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coin_configs'

    def __str__(self):
        return f"Coin Config (cashback={self.cashback_percentage} paise per ₹100, coin=₹{self.coin_value_rupees})"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @staticmethod
    def get_active() -> 'CoinConfig':
        obj, _ = CoinConfig.objects.get_or_create(pk=1)
        return obj
