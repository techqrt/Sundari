from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.create_portfolio import CreatePortfolioSerializer
from sunndari_apps.artists.serializers.request.update.update_portfolio import UpdatePortfolioSerializer
from sunndari_apps.artists.serializers.request.get.get_portfolio import GetPortfolioSerializer
from sunndari_apps.artists.serializers.request.delete.delete_portfolio import DeletePortfolioSerializer
from sunndari_apps.artists.serializers.response.get.get_portfolio import PortfolioResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_portfolio import PortfolioResponseGetAllSerializer
from sunndari_apps.artists.views.portfolio import PortfolioView


class PortfolioController:

    @extend_schema(
        description='Upload a portfolio item (image or video). Max 20 active items.',
        request=CreatePortfolioSerializer,
        responses=SwaggerPage.response(description='Portfolio item added successfully'),
        tags=['Artists - Portfolio'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreatePortfolioSerializer).validate
    def create_portfolio(request: Request) -> Response:
        file = request.FILES.get('file')
        return PortfolioView().create_extract(params=request.params, file=file)

    @extend_schema(
        description='Update a portfolio item caption, sub-category, or active status.',
        request=UpdatePortfolioSerializer,
        responses=SwaggerPage.response(description='Portfolio item updated successfully'),
        tags=['Artists - Portfolio'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdatePortfolioSerializer).validate
    def update_portfolio(request: Request) -> Response:
        return PortfolioView().update_extract(params=request.params)

    @extend_schema(
        description='Delete a portfolio item.',
        parameters=DeletePortfolioSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Portfolio item deleted successfully'),
        tags=['Artists - Portfolio'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DeletePortfolioSerializer).validate
    def delete_portfolio(request: Request) -> Response:
        return PortfolioView().delete_extract(params=request.params)

    @extend_schema(
        description='Get a single portfolio item.',
        parameters=GetPortfolioSerializer.get_parameters(),
        responses=SwaggerPage.response(response=PortfolioResponseSerializer),
        tags=['Artists - Portfolio'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetPortfolioSerializer).validate
    def get_portfolio(request: Request) -> Response:
        return PortfolioView().get_extract(params=request.params)

    @extend_schema(
        description='Get all portfolio items for own artist profile, or any artist profile by artist_id.',
        parameters=SwaggerPage.get_all_parameters() + [
            OpenApiParameter(
                name='artist_id', description='ID of the artist (omit to get own portfolio)',
                required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
            ),
        ],
        responses=SwaggerPage.response(response=PortfolioResponseGetAllSerializer),
        tags=['Artists - Portfolio'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_portfolio(request: Request) -> Response:
        return PortfolioView().get_all_extract(params=request.params)
