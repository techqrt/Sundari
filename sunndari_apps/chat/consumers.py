from asgiref.sync import async_to_sync
from redis.exceptions import RedisError
from channels.generic.websocket import JsonWebsocketConsumer
from sunndari_apps.chat.services import ChatService
from sunndari.constants import Constants


class ChatConsumer(JsonWebsocketConsumer):
    """Sync consumer — the rest of the codebase is fully synchronous Django/DRF,
    so this calls the existing ORM/service code directly rather than introducing
    async ORM access patterns found nowhere else in the project."""

    def group_name(self, booking_id) -> str:
        return f'chat_{booking_id}'

    def connect(self):
        user = self.scope.get('user')
        booking_id = self.scope['url_route']['kwargs']['booking_id']

        if user is None:
            self.close(code=4401)
            return

        try:
            booking = ChatService.get_booking_or_raise(booking_id=booking_id)
            ChatService.assert_participant(booking=booking, user_id=user.user_id)
        except ValueError:
            self.close(code=4403)
            return

        try:
            async_to_sync(self.channel_layer.group_add)(self.group_name(booking_id), self.channel_name)
        except RedisError:
            # The channel layer (Redis) being unreachable must not surface as an
            # unhandled 500 on the handshake — reject cleanly so the client can retry.
            self.close(code=4503)
            return
        self.booking_id = booking_id
        self.user_id = user.user_id
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, 'booking_id'):
            try:
                async_to_sync(self.channel_layer.group_discard)(
                    self.group_name(self.booking_id), self.channel_name,
                )
            except RedisError:
                pass

    def receive_json(self, content, **kwargs):
        if content.get('type') != 'message.send':
            self.send_json({'type': 'error', 'reason': 'Unknown message type'})
            return

        try:
            message = ChatService.send_message(
                booking_id=self.booking_id, user_id=self.user_id, content=content.get('content', ''),
            )
        except ValueError as e:
            reason = 'conversation_closed' if str(e) in (Constants.conversation_closed, Constants.chat_not_eligible) else str(e)
            self.send_json({'type': 'message.rejected', 'reason': reason})
            return

        message_payload = {
            'id': message['message_id'],
            'senderId': message['sender_id'],
            'content': message['content'],
            'createdAt': message['created_at'].isoformat(),
        }
        try:
            async_to_sync(self.channel_layer.group_send)(
                self.group_name(self.booking_id),
                {'type': 'chat.message', 'message': message_payload},
            )
        except RedisError:
            # Already persisted by ChatService.send_message — only the realtime
            # broadcast failed. Echo to the sender directly so their own UI still
            # reflects it; the other party picks it up on next fetch/reconnect.
            self.send_json({'type': 'message.created', 'message': message_payload})

    # ── Group event handlers (dispatched by Channels via the "type" key) ──

    def chat_message(self, event):
        self.send_json({'type': 'message.created', 'message': event['message']})

    def chat_closed(self, event):
        self.send_json({'type': 'conversation.closed', 'reason': event.get('reason', 'appointment_completed')})
