from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.artists.serializers.request.create.create_addon import CreateAddOnSerializer
from sunndari_apps.artists.serializers.request.update.update_addon import UpdateAddOnSerializer
from sunndari_apps.artists.serializers.request.delete.delete_addon import DeleteAddOnSerializer
from sunndari_apps.artists.serializers.request.get.get_addon import GetAddOnSerializer
from sunndari_apps.artists.serializers.response.get.get_addon import AddOnResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_addon import AddOnResponseGetAllSerializer
from sunndari_apps.artists.views.addon import AddOnView


class AddOnController:

    @extend_schema(
        description=(
            'Create an add-on (extra service) and link it to packages of your own via package_ids. '
            'duration_minutes is extra appointment time (0 = none).'
        ),
        request=CreateAddOnSerializer,
        responses=SwaggerPage.response(description='Add-on created successfully'),
        tags=['Artists - Add-ons'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateAddOnSerializer).validate
    def create_addon(request: Request) -> Response:
        return AddOnView().create_extract(params=request.params)

    @extend_schema(
        description='Update an add-on. Sending package_ids replaces the linked packages; omit to keep them. Existing bookings are unaffected.',
        request=UpdateAddOnSerializer,
        responses=SwaggerPage.response(description='Add-on updated successfully'),
        tags=['Artists - Add-ons'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateAddOnSerializer).validate
    def update_addon(request: Request) -> Response:
        return AddOnView().update_extract(params=request.params)

    @extend_schema(
        description='Delete an add-on. Existing bookings keep their own snapshot of it.',
        parameters=DeleteAddOnSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Add-on deleted successfully'),
        tags=['Artists - Add-ons'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DeleteAddOnSerializer).validate
    def delete_addon(request: Request) -> Response:
        return AddOnView().delete_extract(params=request.params)

    @extend_schema(
        description='Get one of your add-ons with the packages it applies to.',
        parameters=GetAddOnSerializer.get_parameters(),
        responses=SwaggerPage.response(response=AddOnResponseSerializer),
        tags=['Artists - Add-ons'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAddOnSerializer).validate
    def get_addon(request: Request) -> Response:
        return AddOnView().get_extract(params=request.params)

    @extend_schema(
        description='List your add-ons, or (with artist_id) the active add-ons of an approved artist.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=AddOnResponseGetAllSerializer),
        tags=['Artists - Add-ons'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_addons(request: Request) -> Response:
        return AddOnView().get_all_extract(params=request.params)
