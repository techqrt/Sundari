from rest_framework import serializers


class RegistrationFeeSerializer(serializers.Serializer):
    feeAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    paid = serializers.BooleanField()
    exempt = serializers.BooleanField()
    registrationRequired = serializers.BooleanField()
    paidAt = serializers.DateTimeField(allow_null=True)


class RegistrationFeeResponseSerializer(serializers.Serializer):
    data = RegistrationFeeSerializer()


class PromoQuoteSerializer(serializers.Serializer):
    promoCode = serializers.CharField(allow_null=True)
    feeAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    discountPercent = serializers.DecimalField(max_digits=5, decimal_places=2)
    discountAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payableAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    requiresPayment = serializers.BooleanField()


class PromoQuoteResponseSerializer(serializers.Serializer):
    data = PromoQuoteSerializer()


class InitiateRegistrationPaymentDataSerializer(serializers.Serializer):
    registration_payment_id = serializers.IntegerField()
    gateway_order_id = serializers.CharField(allow_null=True)
    razorpay_key_id = serializers.CharField(allow_null=True)
    amount = serializers.IntegerField(help_text='Amount in paise; 0 when a 100% promo covered the fee.')
    currency = serializers.CharField()
    fee_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payable_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    fully_covered_by_promo = serializers.BooleanField()


class InitiateRegistrationPaymentResponseSerializer(serializers.Serializer):
    data = InitiateRegistrationPaymentDataSerializer()
