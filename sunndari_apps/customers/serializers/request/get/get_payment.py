from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.customers.dataclasses.request.get.get_payment import GetPaymentRequest


class GetPaymentSerializer(GetSerializer):
    payment_id = serializers.IntegerField()

    def create(self, validated_data) -> GetPaymentRequest:
        return GetPaymentRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='payment_id', description='ID of the payment',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
