from rest_framework import serializers


class ConversationSerializer(serializers.Serializer):
    conversationId = serializers.IntegerField()
    bookingId = serializers.IntegerField()
    isOpen = serializers.BooleanField()
    createdAt = serializers.DateTimeField()


class ConversationResponseSerializer(serializers.Serializer):
    data = ConversationSerializer()


class MessageSerializer(serializers.Serializer):
    messageId = serializers.IntegerField()
    conversationId = serializers.IntegerField()
    senderId = serializers.IntegerField()
    content = serializers.CharField()
    createdAt = serializers.DateTimeField()


class MessageResponseSerializer(serializers.Serializer):
    data = MessageSerializer()
