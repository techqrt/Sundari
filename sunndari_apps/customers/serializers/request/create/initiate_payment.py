from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.create.initiate_payment import InitiatePaymentRequest


class InitiatePaymentSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    payment_type = serializers.ChoiceField(choices=['full', 'advance', 'balance'], required=False, default='full')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    def create(self, validated_data) -> InitiatePaymentRequest:
        return InitiatePaymentRequest(**validated_data)
