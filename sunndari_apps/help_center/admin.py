from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.help_center.models import (
    SupportConversation, SupportMessage, SupportTicket, SupportTicketAttachment,
)


@admin.register(SupportConversation)
class SupportConversationAdmin(ModelAdmin):
    list_display = ('conversation_id', 'customer', 'subject', 'status', 'created_at')
    search_fields = ('subject', 'customer__name', 'customer__phone_number')


admin.site.register(SupportMessage, ModelAdmin)
admin.site.register(SupportTicket, ModelAdmin)
admin.site.register(SupportTicketAttachment, ModelAdmin)
