from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.views.brand import BrandView


class BrandController:

    @extend_schema(
        description='Active brands (admin-managed), alphabetical. search_key filters by name.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(description='Brands'),
        tags=['Core - Brands'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_brands(request: Request) -> Response:
        return BrandView().get_all_extract(params=request.params)
