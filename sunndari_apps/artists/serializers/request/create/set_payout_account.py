import re
from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.set_payout_account import SetPayoutAccountRequest

IFSC_PATTERN = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')


class SetPayoutAccountSerializer(serializers.Serializer):
    account_holder_name = serializers.CharField(max_length=200)
    bank_account_number = serializers.RegexField(r'^[0-9]{6,30}$', error_messages={'invalid': 'Bank account number must be 6-30 digits.'})
    ifsc_code = serializers.CharField(max_length=11, min_length=11)
    upi_id = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate_ifsc_code(self, value):
        if not IFSC_PATTERN.match(value.upper()):
            raise serializers.ValidationError('Invalid IFSC code format')
        return value.upper()

    def create(self, validated_data) -> SetPayoutAccountRequest:
        return SetPayoutAccountRequest(**validated_data)
