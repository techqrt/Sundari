from django.contrib import admin
from sunndari_apps.users.models.customer_address import CustomerAddress


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ('address_id', 'user', 'address_line_1', 'city', 'pin_code', 'is_default')
    list_filter = ('is_default', 'city')
    search_fields = ('address_line_1', 'city', 'pin_code')
    readonly_fields = ('address_id', 'created_at')
