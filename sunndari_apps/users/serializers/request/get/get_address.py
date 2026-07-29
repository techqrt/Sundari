from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.users.dataclasses.request.get.get_address import CustomerAddressGetRequest
from sunndari_apps.common.swagger import SwaggerPage


class CustomerAddressGetSerializer(GetSerializer):
    address_id = serializers.IntegerField()

    def create(self, validated_data) -> CustomerAddressGetRequest:
        return CustomerAddressGetRequest(**validated_data)

    @staticmethod
    def get_parameters(default_parameters: list = None) -> list:
        if default_parameters is None:
            default_parameters = SwaggerPage.get_parameters()
        default_parameters.append(OpenApiParameter(
            name='address_id', description='ID of the address',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY
        ))
        return default_parameters
