from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.serializers.request.get.get_service_sub_category import ServiceSubCategoryGetSerializer
from sunndari_apps.core.serializers.response.get.get_service_sub_category import ServiceSubCategoryResponseGetSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_service_sub_category import ServiceSubCategoryResponseGetAllSerializer
from sunndari_apps.core.views.service_sub_category import ServiceSubCategoryView


class ServiceSubCategoryController:

    @extend_schema(
        description='Get a service sub-category by ID.',
        parameters=ServiceSubCategoryGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ServiceSubCategoryResponseGetSerializer),
        tags=['Core - Service Sub-Category'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=ServiceSubCategoryGetSerializer).validate
    def get_service_sub_category(request: Request) -> Response:
        return ServiceSubCategoryView().get_extract(params=request.params)

    @extend_schema(
        description='Get all service sub-categories. Filter by categoryId to get services under a specific category.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=ServiceSubCategoryResponseGetAllSerializer),
        tags=['Core - Service Sub-Category'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_service_sub_categories(request: Request) -> Response:
        return ServiceSubCategoryView().get_all_extract(params=request.params)
