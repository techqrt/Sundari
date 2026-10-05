from django.urls import path
from sunndari_apps.help_center.controllers.conversation import ConversationController
from sunndari_apps.help_center.controllers.message import MessageController
from sunndari_apps.help_center.controllers.artist_conversation import ArtistConversationController
from sunndari_apps.help_center.controllers.artist_message import ArtistMessageController
from sunndari_apps.help_center.controllers.admin_conversation import AdminConversationController
from sunndari_apps.help_center.controllers.admin_message import AdminMessageController
from sunndari_apps.help_center.views.admin_page import admin_chat_page
from sunndari_apps.help_center.controllers.ticket import TicketController

urlpatterns = [
    path('conversation/get/', ConversationController.get_conversation, name='help_center_get_conversation'),
    path('messages/get_all/', MessageController.get_all_messages, name='help_center_get_all_messages'),
    path('messages/create/', MessageController.create_message, name='help_center_create_message'),

    path('artist/conversation/get/', ArtistConversationController.get_conversation, name='help_center_artist_get_conversation'),
    path('artist/messages/get_all/', ArtistMessageController.get_all_messages, name='help_center_artist_get_all_messages'),
    path('artist/messages/create/', ArtistMessageController.create_message, name='help_center_artist_create_message'),

    path('admin/conversations/get_all/', AdminConversationController.get_all_conversations, name='help_center_admin_get_all_conversations'),
    path('admin/conversation/get/', AdminConversationController.get_conversation, name='help_center_admin_get_conversation'),
    path('admin/conversation/close/', AdminConversationController.close_conversation, name='help_center_admin_close_conversation'),
    path('admin/messages/get_all/', AdminMessageController.get_all_messages, name='help_center_admin_get_all_messages'),
    path('admin/messages/create/', AdminMessageController.create_message, name='help_center_admin_create_message'),

    path('tickets/create/', TicketController.create_ticket, name='help_center_create_ticket'),
    path('tickets/get/', TicketController.get_ticket, name='help_center_get_ticket'),
    path('tickets/get_all/', TicketController.get_all_tickets, name='help_center_get_all_tickets'),
    path('tickets/close/', TicketController.close_ticket, name='help_center_close_ticket'),
    path('tickets/attachment/', TicketController.download_attachment, name='help_center_ticket_attachment'),
    path('admin/tickets/get_all/', TicketController.admin_get_all_tickets, name='help_center_admin_get_all_tickets'),
    path('admin/tickets/get/', TicketController.admin_get_ticket, name='help_center_admin_get_ticket'),
    path('admin/tickets/update_status/', TicketController.admin_update_ticket_status, name='help_center_admin_update_ticket_status'),

    path('admin/chat/', admin_chat_page, name='help_center_admin_chat_page'),
]
