from django.urls import path
from sunndari_apps.help_center.controllers.conversation import ConversationController
from sunndari_apps.help_center.controllers.message import MessageController
from sunndari_apps.help_center.controllers.admin_conversation import AdminConversationController
from sunndari_apps.help_center.controllers.admin_message import AdminMessageController

urlpatterns = [
    path('conversation/get/', ConversationController.get_conversation, name='help_center_get_conversation'),
    path('messages/get_all/', MessageController.get_all_messages, name='help_center_get_all_messages'),
    path('messages/create/', MessageController.create_message, name='help_center_create_message'),

    path('admin/conversations/get_all/', AdminConversationController.get_all_conversations, name='help_center_admin_get_all_conversations'),
    path('admin/conversation/get/', AdminConversationController.get_conversation, name='help_center_admin_get_conversation'),
    path('admin/conversation/close/', AdminConversationController.close_conversation, name='help_center_admin_close_conversation'),
    path('admin/messages/get_all/', AdminMessageController.get_all_messages, name='help_center_admin_get_all_messages'),
    path('admin/messages/create/', AdminMessageController.create_message, name='help_center_admin_create_message'),
]
