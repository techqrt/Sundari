from rest_framework import serializers


class PayoutAccountSerializer(serializers.Serializer):
    payoutAccountId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    accountHolderName = serializers.CharField()
    bankAccountNumberMasked = serializers.CharField()
    ifscCode = serializers.CharField()
    upiId = serializers.CharField(allow_null=True, allow_blank=True)
    verificationStatusId = serializers.IntegerField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PayoutAccountResponseSerializer(serializers.Serializer):
    data = PayoutAccountSerializer()
