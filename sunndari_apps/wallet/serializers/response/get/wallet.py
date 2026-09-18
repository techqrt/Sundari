from rest_framework import serializers


class WalletSerializer(serializers.Serializer):
    customerId = serializers.IntegerField()
    balanceCoins = serializers.IntegerField()
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class WalletResponseSerializer(serializers.Serializer):
    data = WalletSerializer()
