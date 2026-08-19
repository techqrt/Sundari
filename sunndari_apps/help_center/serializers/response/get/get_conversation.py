from rest_framework import serializers


class SupportConversationSerializer(serializers.Serializer):
    conversationId = serializers.IntegerField()
    customerId = serializers.IntegerField()
    status = serializers.CharField()
    createdAt = serializers.DateTimeField()
    closedAt = serializers.DateTimeField(allow_null=True)


class SupportConversationResponseSerializer(serializers.Serializer):
    data = SupportConversationSerializer()


class SupportMessageSerializer(serializers.Serializer):
    messageId = serializers.IntegerField()
    conversationId = serializers.IntegerField()
    senderId = serializers.IntegerField()
    content = serializers.CharField()
    createdAt = serializers.DateTimeField()


class SupportMessageResponseSerializer(serializers.Serializer):
    data = SupportMessageSerializer()
