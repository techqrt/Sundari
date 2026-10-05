from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.help_center.models import (
    SupportConversation, SupportMessage, SupportTicket, SupportTicketAttachment,
)

admin.site.register(SupportConversation, ModelAdmin)
admin.site.register(SupportMessage, ModelAdmin)
admin.site.register(SupportTicket, ModelAdmin)
admin.site.register(SupportTicketAttachment, ModelAdmin)
