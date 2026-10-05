from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.update.reply_review import ReplyReviewSerializer
from sunndari_apps.artists.views.review import ArtistReviewView
from sunndari_apps.customers.serializers.response.get_all.get_all_review import ReviewResponseGetAllSerializer


class ArtistReviewController:

    @extend_schema(
        description='Reviews customers wrote about you (with your replies), newest first by default; each entry includes customerName.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Reviews'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_reviews(request: Request) -> Response:
        return ArtistReviewView().get_all_extract(params=request.params)

    @extend_schema(
        description='Reply to a review of yours (shown with the review to everyone). Calling again edits your reply.',
        request=ReplyReviewSerializer,
        responses=SwaggerPage.response(description='OK'),
        tags=['Artists - Reviews'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ReplyReviewSerializer).validate
    def reply_review(request: Request) -> Response:
        return ArtistReviewView().reply_extract(params=request.params)
