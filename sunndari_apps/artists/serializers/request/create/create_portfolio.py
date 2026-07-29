from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.create_portfolio import CreatePortfolioRequest


class CreatePortfolioSerializer(serializers.Serializer):
    media_type = serializers.ChoiceField(choices=['image', 'video'])
    sub_category_id = serializers.IntegerField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def create(self, validated_data) -> CreatePortfolioRequest:
        return CreatePortfolioRequest(**validated_data)
