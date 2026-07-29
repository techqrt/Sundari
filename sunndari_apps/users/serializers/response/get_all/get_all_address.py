from rest_framework import serializers
from sunndari_apps.users.serializers.response.get.get_address import CustomerAddressGetSerializer


class CustomerAddressGetAllSerializer(serializers.Serializer):
    data = serializers.ListField(child=CustomerAddressGetSerializer())
    presentPage = serializers.IntegerField()
    totalPage = serializers.IntegerField()


class CustomerAddressResponseGetAllSerializer(serializers.Serializer):
    data = CustomerAddressGetAllSerializer()
