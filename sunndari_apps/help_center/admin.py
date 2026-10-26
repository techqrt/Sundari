from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.common.admin_columns import related_column, preview_column
from sunndari_apps.help_center.models import (
    SupportConversation, SupportMessage, SupportTicket, SupportTicketAttachment,
)


@admin.register(SupportConversation)
class SupportConversationAdmin(ModelAdmin):
    list_display = ('conversation_id', 'customer', 'subject', 'status', 'created_at')
    search_fields = ('subject', 'customer__name', 'customer__phone_number')




@admin.register(SupportMessage)
class SupportMessageAdmin(ModelAdmin):
    list_display = ('message_id', 'conversation', 'sender_name', 'content_preview', 'created_at')
    search_fields = ('content', 'sender__name', 'sender__phone_number')
    list_select_related = ('conversation', 'sender')
    sender_name = related_column('Sender', 'sender__name', 'sender__phone_number')
    content_preview = preview_column('Message', 'content')


@admin.register(SupportTicket)
class SupportTicketAdmin(ModelAdmin):
    list_display = ('ticket_id', 'user_name', 'issue_type', 'subject', 'status', 'booking', 'created_at')
    list_filter = ('status', 'issue_type')
    search_fields = ('subject', 'description', 'user__name', 'user__phone_number')
    list_select_related = ('user', 'booking')
    date_hierarchy = 'created_at'
    user_name = related_column('User', 'user__name', 'user__phone_number')


@admin.register(SupportTicketAttachment)
class SupportTicketAttachmentAdmin(ModelAdmin):
    list_display = ('attachment_id', 'ticket_subject', 'user_name', 'created_at')
    search_fields = ('ticket__subject', 'ticket__user__name', 'ticket__user__phone_number')
    list_select_related = ('ticket__user',)
    ticket_subject = related_column('Ticket', 'ticket__subject')
    user_name = related_column('User', 'ticket__user__name', 'ticket__user__phone_number')
