from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.users.dataclasses.request.delete.delete_address import CustomerAddressDeleteRequest


class CustomerAddressDeleteSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()

    def create(self, validated_data) -> CustomerAddressDeleteRequest:
        return CustomerAddressDeleteRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='address_id', description='ID of the address to delete',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
            )
        ]
