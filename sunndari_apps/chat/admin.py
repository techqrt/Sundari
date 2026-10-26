from django.contrib import admin
from unfold.admin import ModelAdmin
from sunndari_apps.chat.models import Conversation, Message
from sunndari_apps.common.admin_columns import related_column, preview_column


@admin.register(Conversation)
class ConversationAdmin(ModelAdmin):
    list_display = ('conversation_id', 'booking', 'customer_name', 'artist_name', 'created_at')
    search_fields = (
        'booking__customer__name', 'booking__customer__phone_number',
        'booking__artist__user__name', 'booking__artist__user__phone_number',
    )
    list_select_related = ('booking__customer', 'booking__artist__user')
    customer_name = related_column('Customer', 'booking__customer__name', 'booking__customer__phone_number')
    artist_name = related_column('Artist', 'booking__artist__user__name', 'booking__artist__user__phone_number')


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ('message_id', 'conversation', 'sender_name', 'content_preview', 'created_at')
    search_fields = ('content', 'sender__name', 'sender__phone_number')
    list_select_related = ('conversation', 'sender')
    sender_name = related_column('Sender', 'sender__name', 'sender__phone_number')
    content_preview = preview_column('Message', 'content')
