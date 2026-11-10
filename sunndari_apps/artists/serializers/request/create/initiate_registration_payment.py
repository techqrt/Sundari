from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.initiate_registration_payment import (
    InitiateRegistrationPaymentRequest,
)


class InitiateRegistrationPaymentSerializer(serializers.Serializer):
    promo_code = serializers.CharField(max_length=40, required=False, allow_blank=True, allow_null=True)

    def create(self, validated_data) -> InitiateRegistrationPaymentRequest:
        return InitiateRegistrationPaymentRequest(**validated_data)
