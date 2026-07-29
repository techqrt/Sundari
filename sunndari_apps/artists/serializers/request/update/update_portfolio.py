from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.update.update_portfolio import UpdatePortfolioRequest


class UpdatePortfolioSerializer(serializers.Serializer):
    portfolio_id = serializers.IntegerField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=300)
    sub_category_id = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)

    def create(self, validated_data) -> UpdatePortfolioRequest:
        return UpdatePortfolioRequest(**validated_data)
