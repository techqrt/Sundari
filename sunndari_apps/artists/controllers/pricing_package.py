from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.create_package import CreatePackageSerializer
from sunndari_apps.artists.serializers.request.update.update_package import UpdatePackageSerializer
from sunndari_apps.artists.serializers.request.get.get_package import GetPackageSerializer
from sunndari_apps.artists.serializers.request.delete.delete_package import DeletePackageSerializer
from sunndari_apps.artists.serializers.response.get.get_package import PackageResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_package import PackageResponseGetAllSerializer
from sunndari_apps.artists.views.pricing_package import PricingPackageView


class PricingPackageController:

    @extend_schema(
        description='Create a pricing package. Price must be ≥ ₹500.',
        request=CreatePackageSerializer,
        responses=SwaggerPage.response(description='Package created successfully'),
        tags=['Artists - Packages'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreatePackageSerializer).validate
    def create_package(request: Request) -> Response:
        return PricingPackageView().create_extract(params=request.params)

    @extend_schema(
        description='Update a pricing package and replace its inclusions.',
        request=UpdatePackageSerializer,
        responses=SwaggerPage.response(description='Package updated successfully'),
        tags=['Artists - Packages'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdatePackageSerializer).validate
    def update_package(request: Request) -> Response:
        return PricingPackageView().update_extract(params=request.params)

    @extend_schema(
        description='Delete a package. Artist must retain at least 1 active package.',
        parameters=DeletePackageSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Package deleted successfully'),
        tags=['Artists - Packages'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DeletePackageSerializer).validate
    def delete_package(request: Request) -> Response:
        return PricingPackageView().delete_extract(params=request.params)

    @extend_schema(
        description='Get a single package with its inclusions.',
        parameters=GetPackageSerializer.get_parameters(),
        responses=SwaggerPage.response(response=PackageResponseSerializer),
        tags=['Artists - Packages'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetPackageSerializer).validate
    def get_package(request: Request) -> Response:
        return PricingPackageView().get_extract(params=request.params)

    @extend_schema(
        description='Get all packages for own artist profile, or any artist profile by artist_id.',
        parameters=SwaggerPage.get_all_parameters() + [
            OpenApiParameter(
                name='artist_id', description='ID of the artist (omit to get own packages)',
                required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ],
        responses=SwaggerPage.response(response=PackageResponseGetAllSerializer),
        tags=['Artists - Packages'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_packages(request: Request) -> Response:
        return PricingPackageView().get_all_extract(params=request.params)
