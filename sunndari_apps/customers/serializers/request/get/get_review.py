from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.common.serializers.request.get import GetSerializer
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.customers.dataclasses.request.get.get_review import GetReviewRequest


class GetReviewSerializer(GetSerializer):
    review_id = serializers.IntegerField()

    def create(self, validated_data) -> GetReviewRequest:
        return GetReviewRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_parameters()
        params.append(OpenApiParameter(
            name='review_id', description='ID of the review',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        return params
