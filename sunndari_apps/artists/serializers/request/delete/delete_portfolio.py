from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_portfolio import DeletePortfolioRequest


class DeletePortfolioSerializer(serializers.Serializer):
    portfolio_id = serializers.IntegerField()

    def create(self, validated_data) -> DeletePortfolioRequest:
        return DeletePortfolioRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='portfolio_id', description='ID of the portfolio item to delete',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
