from django.db import models
from django.db.models import Q
from django.utils import timezone


class SupportConversation(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('running', 'Running'),
        ('closed', 'Closed'),
    ]

    conversation_id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='support_conversations',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'support_conversations'
        indexes = [
            models.Index(fields=['customer', 'status']),
        ]

    def __str__(self):
        return f"Support Conversation #{self.conversation_id} (Customer #{self.customer_id})"

    VALUES_FIELDS = ('conversation_id', 'customer_id', 'status', 'created_at', 'closed_at')

    def create(self, customer_id: int) -> int:
        self.customer_id = customer_id
        self.save()
        return self.conversation_id

    @staticmethod
    def get(conversation_id: int) -> dict:
        return SupportConversation.objects.filter(
            conversation_id=conversation_id,
        ).values(*SupportConversation.VALUES_FIELDS).first()

    @staticmethod
    def get_open_for_customer(customer_id: int) -> dict:
        return SupportConversation.objects.filter(
            customer_id=customer_id,
        ).exclude(status='closed').order_by('-created_at').values(*SupportConversation.VALUES_FIELDS).first()

    @staticmethod
    def get_or_create_for_customer(customer_id: int) -> dict:
        existing = SupportConversation.get_open_for_customer(customer_id=customer_id)
        if existing:
            return existing
        conversation_id = SupportConversation().create(customer_id=customer_id)
        return SupportConversation.get(conversation_id=conversation_id)

    @staticmethod
    def get_all(
        status: str = '',
        sort_by: str = '',
        sort_order: str = 'desc',
        search_key: str = '',
    ) -> list:
        data = SupportConversation.objects.all()
        if status:
            data = data.filter(status=status)
        if search_key:
            data = data.filter(
                Q(customer__name__icontains=search_key) | Q(customer__phone_number__icontains=search_key)
            )
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*SupportConversation.VALUES_FIELDS))

    @staticmethod
    def mark_running(conversation_id: int) -> None:
        SupportConversation.objects.filter(conversation_id=conversation_id, status='open').update(status='running')

    @staticmethod
    def close(conversation_id: int) -> None:
        SupportConversation.objects.filter(conversation_id=conversation_id).update(
            status='closed', closed_at=timezone.now(),
        )
