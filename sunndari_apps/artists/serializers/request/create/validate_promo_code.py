from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.validate_promo_code import ValidatePromoCodeRequest


class ValidatePromoCodeSerializer(serializers.Serializer):
    promo_code = serializers.CharField(max_length=40)

    def create(self, validated_data) -> ValidatePromoCodeRequest:
        return ValidatePromoCodeRequest(**validated_data)
