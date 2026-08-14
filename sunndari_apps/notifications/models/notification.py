from django.db import models
from django.db.models import Q
from django.utils import timezone


class Notification(models.Model):
    TYPE_CHOICES = [
        ('booking_confirmed', 'Booking Confirmed'),
        ('booking_reminder_24h', 'Booking Reminder — 24hr'),
        ('booking_reminder_2h', 'Booking Reminder — 2hr'),
        ('payment_status', 'Payment Status Change'),
        ('new_booking_alert', 'New Booking Alert'),
        ('booking_cancelled', 'Booking Cancelled'),
        ('booking_completed', 'Booking Completed'),
        ('booking_no_show', 'Booking No-Show'),
        ('generic', 'Generic'),
    ]
    DELIVERY_STATUS_CHOICES = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')]

    notification_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    booking = models.ForeignKey(
        'customers.Booking',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='generic')
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    # Delivery fields stay at their stub defaults until an FCM project is confirmed and
    # NotificationGateway.send() is swapped for the real firebase-admin call.
    delivery_status = models.CharField(max_length=10, choices=DELIVERY_STATUS_CHOICES, default='pending')
    fcm_message_id = models.CharField(max_length=200, null=True, blank=True)
    failure_reason = models.CharField(max_length=300, null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Notification #{self.notification_id} → User #{self.user_id} ({self.type})"

    VALUES_FIELDS = (
        'notification_id', 'user_id', 'booking_id', 'type', 'title', 'message',
        'is_read', 'delivery_status', 'fcm_message_id', 'failure_reason',
        'sent_at', 'created_at', 'updated_at',
    )

    def create(self, user_id: int, title: str, message: str, type: str = 'generic', booking_id: int = None) -> int:
        self.user_id = user_id
        self.booking_id = booking_id
        self.type = type
        self.title = title
        self.message = message
        self.save()
        return self.notification_id

    @staticmethod
    def get(notification_id: int) -> dict:
        return Notification.objects.filter(notification_id=notification_id).values(*Notification.VALUES_FIELDS).first()

    @staticmethod
    def get_all(
        user_id: int = None,
        sort_by: str = '',
        sort_order: str = 'desc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = Notification.objects.all()
        if user_id:
            data = data.filter(user_id=user_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(title__icontains=search_key) | Q(message__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        else:
            data = data.order_by('-created_at')
        return list(data.values(*Notification.VALUES_FIELDS))

    @staticmethod
    def mark_read(notification_id: int) -> None:
        Notification.objects.filter(notification_id=notification_id).update(
            is_read=True, updated_at=timezone.now(),
        )

    @staticmethod
    def mark_all_read(user_id: int) -> int:
        return Notification.objects.filter(user_id=user_id, is_read=False).update(
            is_read=True, updated_at=timezone.now(),
        )

    @staticmethod
    def exists_for_booking(booking_id: int, type: str) -> bool:
        return Notification.objects.filter(booking_id=booking_id, type=type).exists()

    @staticmethod
    def mark_delivery(notification_id: int, delivery_status: str, fcm_message_id: str = None, failure_reason: str = None) -> None:
        Notification.objects.filter(notification_id=notification_id).update(
            delivery_status=delivery_status,
            fcm_message_id=fcm_message_id,
            failure_reason=failure_reason,
            sent_at=timezone.now() if delivery_status == 'sent' else None,
        )
