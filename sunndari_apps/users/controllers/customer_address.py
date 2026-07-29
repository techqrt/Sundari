from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.common.serializers.request.get_all import GetAllSerializer
from sunndari_apps.users.serializers.request.create.create_address import CustomerAddressCreateSerializer
from sunndari_apps.users.serializers.request.update.update_address import CustomerAddressUpdateSerializer
from sunndari_apps.users.serializers.request.get.get_address import CustomerAddressGetSerializer
from sunndari_apps.users.serializers.request.delete.delete_address import CustomerAddressDeleteSerializer
from sunndari_apps.users.serializers.response.get.get_address import CustomerAddressResponseGetSerializer
from sunndari_apps.users.serializers.response.get_all.get_all_address import CustomerAddressResponseGetAllSerializer
from sunndari_apps.users.views.customer_address import CustomerAddressView


class CustomerAddressController:

    @extend_schema(
        description='Add a new address for the logged-in customer (max 5).',
        request=CustomerAddressCreateSerializer,
        responses=SwaggerPage.response(description=CustomerAddressView().create_msg),
        tags=['Users - Address'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CustomerAddressCreateSerializer).validate
    def create_address(request: Request) -> Response:
        return CustomerAddressView().create_extract(params=request.params)

    @extend_schema(
        description='Update an existing address.',
        request=CustomerAddressUpdateSerializer,
        responses=SwaggerPage.response(description=CustomerAddressView().update_msg),
        tags=['Users - Address'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CustomerAddressUpdateSerializer).validate
    def update_address(request: Request) -> Response:
        return CustomerAddressView().update_extract(params=request.params)

    @extend_schema(
        description='Delete an address.',
        parameters=CustomerAddressDeleteSerializer.get_parameters(),
        responses=SwaggerPage.response(description=CustomerAddressView().delete_msg),
        tags=['Users - Address'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CustomerAddressDeleteSerializer).validate
    def delete_address(request: Request) -> Response:
        return CustomerAddressView().delete_extract(params=request.params)

    @extend_schema(
        description='Get a single address by ID.',
        parameters=CustomerAddressGetSerializer.get_parameters(),
        responses=SwaggerPage.response(response=CustomerAddressResponseGetSerializer),
        tags=['Users - Address'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CustomerAddressGetSerializer).validate
    def get_address(request: Request) -> Response:
        return CustomerAddressView().get_extract(params=request.params)

    @extend_schema(
        description='Get all addresses for the logged-in customer.',
        parameters=SwaggerPage.get_all_parameters(),
        responses=SwaggerPage.response(response=CustomerAddressResponseGetAllSerializer),
        tags=['Users - Address'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetAllSerializer).validate
    def get_all_address(request: Request) -> Response:
        return CustomerAddressView().get_all_extract(params=request.params)
