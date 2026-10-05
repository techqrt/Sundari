from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.create_customer_review import CreateCustomerReviewSerializer
from sunndari_apps.artists.views.customer_review import ArtistCustomerReviewView


class ArtistCustomerReviewController:

    @extend_schema(
        description='Rate a customer after a completed booking you served (1-5, once per booking). Private to artists.',
        request=CreateCustomerReviewSerializer,
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Customer reviews'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateCustomerReviewSerializer).validate
    def create_customer_review(request: Request) -> Response:
        return ArtistCustomerReviewView().create_extract(params=request.params)

    @extend_schema(
        description='Customer reviews you wrote. Narrow with filter_key=bookingId or customerId.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Customer reviews'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_customer_reviews(request: Request) -> Response:
        return ArtistCustomerReviewView().get_all_extract(params=request.params)
