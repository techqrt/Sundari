from django.db import models
from django.utils import timezone


class Message(models.Model):
    message_id = models.AutoField(primary_key=True)
    conversation = models.ForeignKey(
        'chat.Conversation',
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='chat_messages',
    )
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'chat_messages'
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"Message #{self.message_id} (Conversation #{self.conversation_id})"

    VALUES_FIELDS = ('message_id', 'conversation_id', 'sender_id', 'content', 'created_at')

    def create(self, conversation_id: int, sender_id: int, content: str) -> int:
        self.conversation_id = conversation_id
        self.sender_id = sender_id
        self.content = content
        self.save()
        return self.message_id

    @staticmethod
    def get_all(conversation_id: int, sort_order: str = 'asc') -> list:
        data = Message.objects.filter(conversation_id=conversation_id)
        data = data.order_by(('-' if sort_order == 'desc' else '') + 'created_at', 'message_id')
        return list(data.values(*Message.VALUES_FIELDS))
