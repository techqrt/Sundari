from rest_framework import serializers
from sunndari_apps.customers.dataclasses.request.create.create_review import CreateReviewRequest


class CreateReviewSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')

    def create(self, validated_data) -> CreateReviewRequest:
        return CreateReviewRequest(**validated_data)
