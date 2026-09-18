from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.wallet.dataclasses.request.get.get_eligible_tiers import GetEligibleTiersRequest


class GetEligibleTiersSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    def create(self, validated_data) -> GetEligibleTiersRequest:
        return GetEligibleTiersRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [
            OpenApiParameter(
                name='booking_id', description='Booking to check redemption eligibility against',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name='amount',
                description="Amount about to be charged (defaults to the booking's remaining amount due)",
                required=False, type=OpenApiTypes.NUMBER, location=OpenApiParameter.QUERY,
            ),
        ]
