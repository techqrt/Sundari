from rest_framework import serializers


class CustomerAddressGetSerializer(serializers.Serializer):
    addressId = serializers.IntegerField()
    userId = serializers.IntegerField()
    addressLine1 = serializers.CharField()
    addressLine2 = serializers.CharField(allow_null=True, allow_blank=True)
    city = serializers.CharField()
    pinCode = serializers.CharField()
    isDefault = serializers.BooleanField()
    createdAt = serializers.DateTimeField()


class CustomerAddressResponseGetSerializer(serializers.Serializer):
    data = CustomerAddressGetSerializer()
