from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.core.serializers.request.get.get_location_type import LocationTypeGetSerializer
from sunndari_apps.core.serializers.response.get.get_location_type import LocationTypeResponseGetSerializer
from sunndari_apps.core.serializers.response.get_all.get_all_location_type import LocationTypeResponseGetAllSerializer
from sunndari_apps.core.views.location_type import LocationTypeView


class LocationTypeController:

    @extend_schema(
        description='Get a location type by ID.',
        parameters=LocationTypeGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=LocationTypeResponseGetSerializer),
        tags=['Core - Location Type'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=LocationTypeGetSerializer).validate
    def get_location_type(request: Request) -> Response:
        return LocationTypeView().get_extract(params=request.params)

    @extend_schema(
        description='Get all location types with pagination.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=LocationTypeResponseGetAllSerializer),
        tags=['Core - Location Type'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_location_types(request: Request) -> Response:
        return LocationTypeView().get_all_extract(params=request.params)
