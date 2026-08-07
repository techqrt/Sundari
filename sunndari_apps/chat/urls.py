from django.urls import path
from sunndari_apps.chat.controllers.conversation import ConversationController
from sunndari_apps.chat.controllers.message import MessageController

urlpatterns = [
    path('conversation/get/', ConversationController.get_conversation, name='chat_get_conversation'),
    path('messages/get_all/', MessageController.get_all_messages, name='chat_get_all_messages'),
    path('messages/create/', MessageController.create_message, name='chat_create_message'),
]
