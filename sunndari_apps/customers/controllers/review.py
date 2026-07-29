from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.customers.serializers.request.create.create_review import CreateReviewSerializer
from sunndari_apps.customers.serializers.request.get.get_review import GetReviewSerializer
from sunndari_apps.customers.serializers.response.get.get_review import ReviewResponseSerializer
from sunndari_apps.customers.serializers.response.get_all.get_all_review import ReviewResponseGetAllSerializer
from sunndari_apps.customers.views.review import ReviewView


class ReviewController:

    @extend_schema(
        description=(
            'Submit a review for a completed booking. One review per booking; updates the '
            "artist's average rating incrementally."
        ),
        request=CreateReviewSerializer,
        responses=SwaggerPage.response(description='Review submitted successfully'),
        tags=['Customers - Reviews'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateReviewSerializer).validate
    def create_review(request: Request) -> Response:
        return ReviewView().create_extract(params=request.params)

    @extend_schema(
        description='Get a single review.',
        parameters=GetReviewSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ReviewResponseSerializer),
        tags=['Customers - Reviews'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetReviewSerializer).validate
    def get_review(request: Request) -> Response:
        return ReviewView().get_extract(params=request.params)

    @extend_schema(
        description='List all reviews for an artist (pass artist_id) — used on the artist detail screen.',
        parameters=SwaggerPage.get_all_parameters() + [
            OpenApiParameter(
                name='artist_id', description='ID of the artist whose reviews to list',
                required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ],
        responses=SwaggerPage.response(response=ReviewResponseGetAllSerializer),
        tags=['Customers - Reviews'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_reviews(request: Request) -> Response:
        return ReviewView().get_all_extract(params=request.params)
