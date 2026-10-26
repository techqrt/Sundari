from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.common.admin_columns import related_column
from sunndari_apps.payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = (
        'payment_id', 'booking', 'customer_name', 'artist_name', 'payment_type', 'amount', 'status', 'gateway', 'paid_at', 'created_at',
    )
    list_filter = ('status', 'payment_type', 'gateway')
    search_fields = (
        'gateway_order_id', 'gateway_payment_id', 'gateway_refund_id',
        'customer__name', 'customer__phone_number', 'artist__user__name', 'artist__user__phone_number',
    )
    list_select_related = ('booking', 'customer', 'artist__user', 'status')
    date_hierarchy = 'created_at'
    customer_name = related_column('Customer', 'customer__name', 'customer__phone_number')
    artist_name = related_column('Artist', 'artist__user__name', 'artist__user__phone_number')
