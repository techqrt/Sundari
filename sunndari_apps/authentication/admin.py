from django.contrib import admin
from sunndari_apps.authentication.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'name', 'phone_number', 'email', 'role', 'is_active', 'created_date_time')
    list_filter = ('role', 'is_active')
    search_fields = ('name', 'phone_number', 'email')
    readonly_fields = ('user_id', 'created_date_time', 'access_token', 'refresh_token')
