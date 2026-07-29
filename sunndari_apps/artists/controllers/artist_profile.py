from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.get.get_profile import ArtistProfileGetSerializer
from sunndari_apps.artists.serializers.request.update.update_profile import ArtistProfileUpdateSerializer
from sunndari_apps.artists.serializers.request.create.add_service import AddServiceSerializer
from sunndari_apps.artists.serializers.request.delete.remove_service import RemoveServiceSerializer
from sunndari_apps.artists.serializers.request.create.add_location import AddLocationSerializer
from sunndari_apps.artists.serializers.request.delete.remove_location import RemoveLocationSerializer
from sunndari_apps.artists.serializers.response.get.get_profile import ArtistProfileResponseSerializer
from sunndari_apps.artists.views.artist_profile import ArtistProfileView


class ArtistProfileController:

    @extend_schema(
        description='Get own artist profile (no artist_id) or any profile by artist_id.',
        parameters=ArtistProfileGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ArtistProfileResponseSerializer),
        tags=['Artists - Profile'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ArtistProfileGetSerializer).validate
    def get_profile(request: Request) -> Response:
        return ArtistProfileView().get_extract(params=request.params)

    @extend_schema(
        description='Update own artist profile. City/radius changes trigger re-approval.',
        request=ArtistProfileUpdateSerializer,
        responses=SwaggerPage.response(description='Profile updated successfully'),
        tags=['Artists - Profile'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ArtistProfileUpdateSerializer).validate
    def update_profile(request: Request) -> Response:
        return ArtistProfileView().update_extract(params=request.params)

    @extend_schema(
        description='Add a service offering to artist profile.',
        request=AddServiceSerializer,
        responses=SwaggerPage.response(description='Service offering added successfully'),
        tags=['Artists - Services'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AddServiceSerializer).validate
    def add_service(request: Request) -> Response:
        return ArtistProfileView().add_service_extract(params=request.params)

    @extend_schema(
        description='Remove a service offering from artist profile.',
        parameters=RemoveServiceSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Service offering removed successfully'),
        tags=['Artists - Services'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RemoveServiceSerializer).validate
    def remove_service(request: Request) -> Response:
        return ArtistProfileView().remove_service_extract(params=request.params)

    @extend_schema(
        description='Get all service offerings for own artist profile, or any artist profile by artist_id.',
        parameters=SwaggerPage.get_all_parameters() + [
            OpenApiParameter(
                name='artist_id', description='ID of the artist (omit to get own service offerings)',
                required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ],
        responses=SwaggerPage.response(description='Data fetched successfully'),
        tags=['Artists - Services'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_services(request: Request) -> Response:
        return ArtistProfileView().get_all_services_extract(params=request.params)

    @extend_schema(
        description='Add a location preference to artist profile.',
        request=AddLocationSerializer,
        responses=SwaggerPage.response(description='Location preference added successfully'),
        tags=['Artists - Locations'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AddLocationSerializer).validate
    def add_location(request: Request) -> Response:
        return ArtistProfileView().add_location_extract(params=request.params)

    @extend_schema(
        description='Remove a location preference from artist profile.',
        parameters=RemoveLocationSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Location preference removed successfully'),
        tags=['Artists - Locations'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RemoveLocationSerializer).validate
    def remove_location(request: Request) -> Response:
        return ArtistProfileView().remove_location_extract(params=request.params)

    @extend_schema(
        description='Get all location preferences for own artist profile, or any artist profile by artist_id.',
        parameters=SwaggerPage.get_all_parameters() + [
            OpenApiParameter(
                name='artist_id', description='ID of the artist (omit to get own location preferences)',
                required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ],
        responses=SwaggerPage.response(description='Data fetched successfully'),
        tags=['Artists - Locations'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_locations(request: Request) -> Response:
        return ArtistProfileView().get_all_locations_extract(params=request.params)
