from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.add_service_area import AddServiceAreaSerializer
from sunndari_apps.artists.serializers.request.update.update_service_area import UpdateServiceAreaSerializer
from sunndari_apps.artists.serializers.request.delete.remove_service_area import RemoveServiceAreaSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_service_area import ServiceAreaResponseGetAllSerializer
from sunndari_apps.artists.views.service_area import ServiceAreaView


class ServiceAreaController:

    @extend_schema(
        description=(
            'Add a city you travel to. travel_charge_type: free, or per_visit with a charge_amount. '
            'per_km is not available yet. Once you have an active area, home visits are only accepted '
            'for addresses in your areas, and the charge is added to the booking total.'
        ),
        request=AddServiceAreaSerializer,
        responses=SwaggerPage.response(description='Service area added successfully'),
        tags=['Artists - Service areas'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AddServiceAreaSerializer).validate
    def add_service_area(request: Request) -> Response:
        return ServiceAreaView().add_extract(params=request.params)

    @extend_schema(
        description='Update a service area. Existing bookings keep the travel fee they were created with.',
        request=UpdateServiceAreaSerializer,
        responses=SwaggerPage.response(description='Service area updated successfully'),
        tags=['Artists - Service areas'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateServiceAreaSerializer).validate
    def update_service_area(request: Request) -> Response:
        return ServiceAreaView().update_extract(params=request.params)

    @extend_schema(
        description='Remove a service area.',
        parameters=RemoveServiceAreaSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Service area removed successfully'),
        tags=['Artists - Service areas'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=RemoveServiceAreaSerializer).validate
    def remove_service_area(request: Request) -> Response:
        return ServiceAreaView().remove_extract(params=request.params)

    @extend_schema(
        description='List your service areas, or (with artist_id) the active areas of an approved artist.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=ServiceAreaResponseGetAllSerializer),
        tags=['Artists - Service areas'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_service_areas(request: Request) -> Response:
        return ServiceAreaView().get_all_extract(params=request.params)
