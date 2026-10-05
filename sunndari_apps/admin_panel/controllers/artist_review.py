from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.admin_panel.serializers.request.update.approve_artist import ApproveArtistSerializer
from sunndari_apps.admin_panel.serializers.request.update.reject_artist import RejectArtistSerializer
from sunndari_apps.admin_panel.serializers.request.get.get_artist_review import GetArtistReviewSerializer
from sunndari_apps.admin_panel.serializers.response.get_all.get_all_artist_review import (
    ArtistReviewQueueResponseGetAllSerializer,
)
from sunndari_apps.admin_panel.views.artist_review import AdminArtistReviewView


class AdminArtistReviewController:

    @extend_schema(
        description='List artists that have submitted onboarding and are awaiting admin review. Admin only.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=ArtistReviewQueueResponseGetAllSerializer),
        tags=['Admin - Artist Review'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_review_queue(request: Request) -> Response:
        return AdminArtistReviewView().get_all_extract(params=request.params)

    @extend_schema(
        description='Approve an artist profile, making it live for bookings. Admin only.',
        request=ApproveArtistSerializer,
        responses=SwaggerPage.response(description='Artist approved successfully'),
        tags=['Admin - Artist Review'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ApproveArtistSerializer).validate
    def approve_artist(request: Request) -> Response:
        return AdminArtistReviewView().approve_extract(params=request.params)

    @extend_schema(
        description='Reject an artist profile with an optional reason. Admin only.',
        request=RejectArtistSerializer,
        responses=SwaggerPage.response(description='Artist rejected'),
        tags=['Admin - Artist Review'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RejectArtistSerializer).validate
    def reject_artist(request: Request) -> Response:
        return AdminArtistReviewView().reject_extract(params=request.params)

    @extend_schema(
        description=(
            "Review details for one artist: registration fields, specialities and work-sample photos. "
            'Admin only. KYC documents are under artists/documents/get_all/.'
        ),
        parameters=GetArtistReviewSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Artist review detail'),
        tags=['Admin - Artist Review'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetArtistReviewSerializer).validate
    def get_review_detail(request: Request) -> Response:
        return AdminArtistReviewView().get_detail_extract(params=request.params)
