from rest_framework import serializers


class TransactionSerializer(serializers.Serializer):
    transactionId = serializers.IntegerField()
    walletId = serializers.IntegerField()
    bookingId = serializers.IntegerField(allow_null=True)
    paymentId = serializers.IntegerField(allow_null=True)
    transactionType = serializers.CharField()
    coins = serializers.IntegerField()
    balanceAfter = serializers.IntegerField()
    remainingCoins = serializers.IntegerField(allow_null=True)
    expiresAt = serializers.DateTimeField(allow_null=True)
    rupeeEquivalent = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    referenceTransactionId = serializers.IntegerField(allow_null=True)
    createdAt = serializers.DateTimeField()


class TransactionGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=TransactionSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class TransactionResponseGetAllSerializer(serializers.Serializer):
    data = TransactionGetAllSerializer()
