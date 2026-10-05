import os
import uuid

from django.db import models
from django.utils import timezone

from sunndari_apps.common.storage import PrivateMediaStorage


class SupportTicket(models.Model):
    """A support issue raised by a customer or an artist. Unlike the running help-center chat
    (one conversation per user), a user can have many tickets, each with its own status,
    optional booking and photo attachments."""

    ISSUE_TYPES = [
        ('booking', 'Booking'), ('payment', 'Payment'), ('service_quality', 'Service quality'),
        ('account', 'Account'), ('technical', 'Technical problem'), ('other', 'Other'),
    ]
    STATUS_CHOICES = [('open', 'Open'), ('in_progress', 'In progress'), ('resolved', 'Resolved'), ('closed', 'Closed')]
    OPEN_STATUSES = ['open', 'in_progress']

    ticket_id = models.AutoField(primary_key=True)
    user = models.ForeignKey('authentication.User', on_delete=models.CASCADE, related_name='support_tickets')
    booking = models.ForeignKey(
        'customers.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets',
    )
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPES)
    subject = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    resolution_note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_tickets'
        indexes = [models.Index(fields=['user', 'status']), models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f"Ticket #{self.ticket_id} ({self.status}) by User #{self.user_id}"


def ticket_attachment_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'support_tickets/ticket_{instance.ticket_id}/{uuid.uuid4().hex}{extension}'


class SupportTicketAttachment(models.Model):
    """Attachments are private (screenshots can show personal details): stored outside the
    public media folder and only served to the ticket's owner or an admin."""

    attachment_id = models.AutoField(primary_key=True)
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=ticket_attachment_upload_path, storage=PrivateMediaStorage())
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'support_ticket_attachments'

    def __str__(self):
        return f"Attachment #{self.attachment_id} (Ticket #{self.ticket_id})"
