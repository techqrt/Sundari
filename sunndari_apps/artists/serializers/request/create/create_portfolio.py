from rest_framework import serializers
from sunndari_apps.artists.dataclasses.request.create.create_portfolio import CreatePortfolioRequest


class CreatePortfolioSerializer(serializers.Serializer):
    media_type = serializers.ChoiceField(choices=['image', 'video'])
    sub_category_id = serializers.IntegerField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=300)
    is_work_sample = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if data.get('is_work_sample') and data['media_type'] != 'image':
            raise serializers.ValidationError({'is_work_sample': 'Work samples must be images.'})
        return data

    def create(self, validated_data) -> CreatePortfolioRequest:
        return CreatePortfolioRequest(**validated_data)
