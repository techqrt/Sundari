from rest_framework import serializers


class NotificationSerializer(serializers.Serializer):
    notificationId = serializers.IntegerField()
    userId = serializers.IntegerField()
    bookingId = serializers.IntegerField(allow_null=True)
    type = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    isRead = serializers.BooleanField()
    deliveryStatus = serializers.CharField()
    fcmMessageId = serializers.CharField(allow_null=True)
    failureReason = serializers.CharField(allow_null=True)
    sentAt = serializers.DateTimeField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class NotificationResponseSerializer(serializers.Serializer):
    data = NotificationSerializer()
