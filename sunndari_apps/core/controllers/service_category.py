from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.serializers.request.get.get_service_category import ServiceCategoryGetSerializer
from sunndari_apps.core.serializers.response.get.get_service_category import ServiceCategoryResponseGetSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_service_category import ServiceCategoryResponseGetAllSerializer
from sunndari_apps.core.views.service_category import ServiceCategoryView


class ServiceCategoryController:

    @extend_schema(
        description='Get a service category by ID.',
        parameters=ServiceCategoryGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ServiceCategoryResponseGetSerializer),
        tags=['Core - Service Category'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ServiceCategoryGetSerializer).validate
    def get_service_category(request: Request) -> Response:
        return ServiceCategoryView().get_extract(params=request.params)

    @extend_schema(
        description='Get all service categories with pagination.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=ServiceCategoryResponseGetAllSerializer),
        tags=['Core - Service Category'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_service_categories(request: Request) -> Response:
        return ServiceCategoryView().get_all_extract(params=request.params)
