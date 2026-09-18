from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.wallet.models import CustomerWallet, CoinTransaction, CoinConfig, RedemptionTier


@admin.register(CoinConfig)
class CoinConfigAdmin(ModelAdmin):
    """Singleton settings row — only one CoinConfig ever exists (save() pins pk=1), so
    the Admin "Add" action is disabled once it's been created the first time (it would
    otherwise silently edit the same row anyway, but showing "Add" then would look like
    it creates a second, independent config). Never deletable — get_active() would just
    recreate it with defaults, silently resetting cashback/redemption rules."""

    list_display = ('cashback_percentage', 'coin_value_rupees', 'coin_expiry_days', 'updated_at')

    def has_add_permission(self, request):
        return not CoinConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RedemptionTier)
class RedemptionTierAdmin(ModelAdmin):
    list_display = ('tier_id', 'rupee_value', 'coin_cost', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    ordering = ('rupee_value',)
    # Derived from rupee_value + the active CoinConfig at save time (see
    # RedemptionTier._resolve_coin_cost) — never hand-edited.
    readonly_fields = ('coin_cost',)


class ReadOnlyModelAdmin(ModelAdmin):
    """Base for models that must only ever change through CustomerWallet.credit()/
    debit()/reverse_redemption() — those hold the row lock and write the matching
    ledger entry atomically, which a raw Admin form save would bypass entirely,
    silently breaking the invariant that balance_coins always matches the ledger."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerWallet)
class CustomerWalletAdmin(ReadOnlyModelAdmin):
    list_display = ('customer', 'balance_coins', 'created_at', 'updated_at')
    search_fields = ('customer__name', 'customer__phone_number')


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyModelAdmin):
    list_display = (
        'transaction_id', 'wallet', 'transaction_type', 'coins',
        'balance_after', 'booking', 'created_at',
    )
    list_filter = ('transaction_type',)
    search_fields = ('wallet__customer__name', 'wallet__customer__phone_number')
    date_hierarchy = 'created_at'
