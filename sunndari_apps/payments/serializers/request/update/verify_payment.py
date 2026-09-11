from rest_framework import serializers
from sunndari_apps.payments.dataclasses.request.update.verify_payment import VerifyPaymentRequest


class VerifyPaymentSerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=200)

    def create(self, validated_data) -> VerifyPaymentRequest:
        return VerifyPaymentRequest(**validated_data)
