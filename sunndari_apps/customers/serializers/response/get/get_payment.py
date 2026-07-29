from rest_framework import serializers


class PaymentSerializer(serializers.Serializer):
    paymentId = serializers.IntegerField()
    bookingId = serializers.IntegerField()
    customerId = serializers.IntegerField()
    artistId = serializers.IntegerField()
    paymentType = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    commissionAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    artistPayoutAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    statusId = serializers.IntegerField()
    gateway = serializers.CharField(allow_null=True)
    gatewayOrderId = serializers.CharField(allow_null=True)
    gatewayPaymentId = serializers.CharField(allow_null=True)
    paidAt = serializers.DateTimeField(allow_null=True)
    failureReason = serializers.CharField(allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()


class PaymentResponseSerializer(serializers.Serializer):
    data = PaymentSerializer()
