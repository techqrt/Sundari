from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.brand_requests import CreateBrandSerializer, UpdateBrandSerializer, DecideBrandRequestSerializer
from sunndari_apps.admin_panel.views.brand import AdminBrandView


class AdminBrandController:

    @extend_schema(description='Add a brand to the list. Admin only.', request=CreateBrandSerializer,
                   responses=SwaggerPage.response(description='Brand created'), tags=['Admin - Brands'])
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateBrandSerializer).validate
    def create_brand(request: Request) -> Response:
        return AdminBrandView().create_extract(params=request.params)

    @extend_schema(description='Rename or (de)activate a brand. Admin only.', request=UpdateBrandSerializer,
                   responses=SwaggerPage.response(description='Brand updated'), tags=['Admin - Brands'])
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateBrandSerializer).validate
    def update_brand(request: Request) -> Response:
        return AdminBrandView().update_extract(params=request.params)

    @extend_schema(description="Artists' brand requests, oldest first. Narrow with filter_key=status&filter_value=pending. Admin only.",
                   parameters=SwaggerPage.get_all_parameters(),
                   responses=SwaggerPage.response(description='Brand requests'), tags=['Admin - Brands'])
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_requests(request: Request) -> Response:
        return AdminBrandView().get_all_requests_extract(params=request.params)

    @extend_schema(description='Approve (adds the brand to the list) or reject a pending brand request. Admin only.',
                   request=DecideBrandRequestSerializer,
                   responses=SwaggerPage.response(description='Decision recorded'), tags=['Admin - Brands'])
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DecideBrandRequestSerializer).validate
    def decide_request(request: Request) -> Response:
        return AdminBrandView().decide_extract(params=request.params)
