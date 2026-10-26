from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.common.admin_columns import related_column
from sunndari_apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ('notification_id', 'user_name', 'type', 'title', 'is_read', 'delivery_status', 'email_sent_at', 'created_at')
    list_filter = ('type', 'is_read', 'delivery_status')
    search_fields = ('user__name', 'user__phone_number', 'user__email', 'title', 'message')
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    user_name = related_column('User', 'user__name', 'user__phone_number')
