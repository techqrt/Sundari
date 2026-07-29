from rest_framework import serializers
from sunndari_apps.users.dataclasses.request.create.create_address import CustomerAddressCreateRequest


class CustomerAddressCreateSerializer(serializers.Serializer):
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(max_length=100)
    pin_code = serializers.CharField(max_length=10)
    is_default = serializers.BooleanField(required=False, default=False)

    def create(self, validated_data) -> CustomerAddressCreateRequest:
        return CustomerAddressCreateRequest(**validated_data)
