from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.update.payment_webhook import PaymentWebhookRequest


class PaymentWebhookSerializer(serializers.Serializer):
    gateway_order_id = serializers.CharField(max_length=100)
    gateway_payment_id = serializers.CharField(max_length=100)
    status = serializers.ChoiceField(choices=['paid', 'failed'])
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> PaymentWebhookRequest:
        return PaymentWebhookRequest(**validated_data)
