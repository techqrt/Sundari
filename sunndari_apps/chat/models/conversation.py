from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    OPEN_BOOKING_STATUSES = ['confirmed', 'in_progress']

    conversation_id = models.AutoField(primary_key=True)
    booking = models.OneToOneField(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='conversation',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'chat_conversations'

    def __str__(self):
        return f"Conversation #{self.conversation_id} (Booking #{self.booking_id})"

    VALUES_FIELDS = ('conversation_id', 'booking_id', 'created_at')

    def create(self, booking_id: int) -> int:
        self.booking_id = booking_id
        self.save()
        return self.conversation_id

    @staticmethod
    def get(conversation_id: int) -> dict:
        return Conversation.objects.filter(conversation_id=conversation_id).values(*Conversation.VALUES_FIELDS).first()

    @staticmethod
    def get_by_booking(booking_id: int) -> dict:
        return Conversation.objects.filter(booking_id=booking_id).values(*Conversation.VALUES_FIELDS).first()

    @staticmethod
    def get_or_create_for_booking(booking_id: int) -> dict:
        obj, _ = Conversation.objects.get_or_create(booking_id=booking_id)
        return Conversation.objects.filter(conversation_id=obj.conversation_id).values(*Conversation.VALUES_FIELDS).first()
