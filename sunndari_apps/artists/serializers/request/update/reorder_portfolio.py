from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.reorder_portfolio import ReorderPortfolioRequest


class ReorderPortfolioSerializer(serializers.Serializer):
    portfolio_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=100)

    def validate_portfolio_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError('portfolio_ids must not contain duplicates.')
        return value

    def create(self, validated_data) -> ReorderPortfolioRequest:
        return ReorderPortfolioRequest(**validated_data)
