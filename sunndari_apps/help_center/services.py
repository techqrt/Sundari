from django.db import transaction
from sunndari_apps.authentication.models import User
from sunndari_apps.help_center.models.conversation import SupportConversation
from sunndari_apps.help_center.models.message import SupportMessage
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class SupportChatService:
    """Single source of truth for Help Center chat eligibility, participant
    authorization, and conversation lifecycle — mirrors chat.services.ChatService
    for the Customer <-> Admin support context."""

    ADMIN_ROLE = 'admin'
    MESSAGE_MAX_LENGTH = 2000

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return User.objects.filter(user_id=user_id, role=SupportChatService.ADMIN_ROLE).exists()

    @staticmethod
    def assert_admin(user_id: int) -> None:
        if not SupportChatService.is_admin(user_id=user_id):
            raise ValueError(Constants.forbidden_resource)

    @staticmethod
    def get_conversation_for_customer(customer_id: int) -> dict:
        conversation = SupportConversation.get_open_for_customer(customer_id=customer_id)
        if not conversation:
            raise ValueError(Constants.conversation_not_found)
        return conversation

    @staticmethod
    def get_conversation_for_admin(conversation_id: int, user_id: int) -> dict:
        SupportChatService.assert_admin(user_id=user_id)
        conversation = SupportConversation.get(conversation_id=conversation_id)
        if not conversation:
            raise ValueError(Constants.conversation_not_found)
        return conversation

    @staticmethod
    def _validate_content(content: str) -> str:
        content = (content or '').strip()
        if not content:
            raise ValueError(Constants.message_empty)
        if len(content) > SupportChatService.MESSAGE_MAX_LENGTH:
            raise ValueError(f'Message content exceeds the {SupportChatService.MESSAGE_MAX_LENGTH} character limit')
        return content

    @staticmethod
    def send_customer_message(customer_id: int, content: str) -> dict:
        content = SupportChatService._validate_content(content=content)

        with transaction.atomic():
            conversation = SupportConversation.get_or_create_for_customer(customer_id=customer_id)
            if conversation['status'] == 'closed':
                raise ValueError(Constants.conversation_closed)
            message_id = SupportMessage().create(
                conversation_id=conversation['conversation_id'], sender_id=customer_id, content=content,
            )
        message = SupportMessage.objects.filter(message_id=message_id).values(*SupportMessage.VALUES_FIELDS).first()

        admin_ids = User.objects.filter(
            role=SupportChatService.ADMIN_ROLE, is_active=True,
        ).values_list('user_id', flat=True)
        for admin_id in admin_ids:
            NotificationService.notify(
                user_id=admin_id,
                title='New Help Center message',
                message=content[:150],
                type='help_center_customer_message',
            )
        return message

    @staticmethod
    def send_admin_message(conversation_id: int, admin_user_id: int, content: str) -> dict:
        content = SupportChatService._validate_content(content=content)
        SupportChatService.assert_admin(user_id=admin_user_id)

        with transaction.atomic():
            conversation = SupportConversation.get(conversation_id=conversation_id)
            if not conversation:
                raise ValueError(Constants.conversation_not_found)
            if conversation['status'] == 'closed':
                raise ValueError(Constants.conversation_closed)
            message_id = SupportMessage().create(
                conversation_id=conversation_id, sender_id=admin_user_id, content=content,
            )
            if conversation['status'] == 'open':
                SupportConversation.mark_running(conversation_id=conversation_id)
        message = SupportMessage.objects.filter(message_id=message_id).values(*SupportMessage.VALUES_FIELDS).first()

        NotificationService.notify(
            user_id=conversation['customer_id'],
            title='Support replied to your message',
            message=content[:150],
            type='help_center_admin_reply',
        )
        return message

    @staticmethod
    def close_conversation(conversation_id: int, admin_user_id: int) -> None:
        SupportChatService.assert_admin(user_id=admin_user_id)
        conversation = SupportConversation.get(conversation_id=conversation_id)
        if not conversation:
            raise ValueError(Constants.conversation_not_found)
        SupportConversation.close(conversation_id=conversation_id)
