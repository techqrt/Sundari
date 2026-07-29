from rest_framework import serializers
from sunndari_apps.users.dataclasses.request.update.update_address import CustomerAddressUpdateRequest


class CustomerAddressUpdateSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    address_line_1 = serializers.CharField(max_length=255, required=False, allow_null=True)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(max_length=100, required=False, allow_null=True)
    pin_code = serializers.CharField(max_length=10, required=False, allow_null=True)
    is_default = serializers.BooleanField(required=False, allow_null=True)

    def create(self, validated_data) -> CustomerAddressUpdateRequest:
        return CustomerAddressUpdateRequest(**validated_data)
