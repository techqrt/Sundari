from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.chat.models.conversation import Conversation
from sunndari_apps.chat.models.message import Message
from sunndari.constants import Constants


class ChatService:
    """Single source of truth for chat eligibility, participant authorization,
    and conversation lifecycle — shared by the HTTP views and the WS consumer
    so the two entry points cannot drift apart."""

    @staticmethod
    def get_booking_or_raise(booking_id: int) -> dict:
        booking = Booking.get(booking_id=booking_id)
        if not booking:
            raise ValueError(Constants.booking_not_found)
        return booking

    @staticmethod
    def is_participant(booking: dict, user_id: int) -> bool:
        if booking['customer_id'] == user_id:
            return True
        artist_user_id = Booking.objects.filter(
            booking_id=booking['booking_id'],
        ).values_list('artist__user_id', flat=True).first()
        return artist_user_id == user_id

    @staticmethod
    def assert_participant(booking: dict, user_id: int) -> None:
        if not ChatService.is_participant(booking=booking, user_id=user_id):
            raise ValueError(Constants.forbidden_resource)

    @staticmethod
    def is_open(booking: dict) -> bool:
        status_name = Booking.objects.filter(
            booking_id=booking['booking_id'],
        ).values_list('status__name', flat=True).first()
        return status_name in Conversation.OPEN_BOOKING_STATUSES

    @staticmethod
    def get_or_create_conversation(booking_id: int, user_id: int) -> dict:
        booking = ChatService.get_booking_or_raise(booking_id=booking_id)
        ChatService.assert_participant(booking=booking, user_id=user_id)
        if not ChatService.is_open(booking=booking):
            existing = Conversation.get_by_booking(booking_id=booking_id)
            if not existing:
                raise ValueError(Constants.chat_not_eligible)
            return existing
        with transaction.atomic():
            return Conversation.get_or_create_for_booking(booking_id=booking_id)

    @staticmethod
    def get_conversation_for_participant(booking_id: int, user_id: int) -> dict:
        booking = ChatService.get_booking_or_raise(booking_id=booking_id)
        ChatService.assert_participant(booking=booking, user_id=user_id)
        conversation = Conversation.get_by_booking(booking_id=booking_id)
        if not conversation:
            raise ValueError(Constants.conversation_not_found)
        return conversation

    @staticmethod
    def send_message(booking_id: int, user_id: int, content: str) -> dict:
        content = (content or '').strip()
        if not content:
            raise ValueError(Constants.message_empty)
        if len(content) > 2000:
            raise ValueError('Message content exceeds the 2000 character limit')

        booking = ChatService.get_booking_or_raise(booking_id=booking_id)
        ChatService.assert_participant(booking=booking, user_id=user_id)

        with transaction.atomic():
            # Re-check status inside the transaction — a connection validated
            # minutes ago must not be trusted for a send happening now.
            if not ChatService.is_open(booking=booking):
                raise ValueError(Constants.conversation_closed)
            conversation = Conversation.get_or_create_for_booking(booking_id=booking_id)
            message_id = Message().create(
                conversation_id=conversation['conversation_id'], sender_id=user_id, content=content,
            )
        return Message.objects.filter(message_id=message_id).values(*Message.VALUES_FIELDS).first()

    @staticmethod
    def close_conversation(booking_id: int) -> None:
        """Called from the booking-completion flow (ArtistBookingView).
        Writability itself is always derived live from booking status — this
        broadcast is purely a UX signal for clients already connected to the
        WS group; it is a no-op if no conversation was ever created."""
        conversation = Conversation.get_by_booking(booking_id=booking_id)
        if not conversation:
            return
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f'chat_{booking_id}',
            {'type': 'chat.closed', 'reason': 'appointment_completed'},
        )
