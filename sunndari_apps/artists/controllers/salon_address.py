from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.artists.serializers.request.create.create_salon_address import CreateSalonAddressSerializer
from sunndari_apps.artists.serializers.request.get.get_salon_addresses import GetSalonAddressesSerializer
from sunndari_apps.artists.serializers.request.update.update_salon_address import UpdateSalonAddressSerializer
from sunndari_apps.artists.serializers.request.delete.delete_salon_address import DeleteSalonAddressSerializer
from sunndari_apps.artists.views.salon_address import SalonAddressView


class SalonAddressController:

    @extend_schema(
        description=(
            'Add a salon or studio address to your own profile; customers choose one of them when they book an '
            'In-Salon appointment. name is what the customer sees (unique among your active addresses, ignoring '
            'case). latitude and longitude are required (decimal degrees; more than six decimals are rounded). '
            'You can have at most 10 active salon addresses. Returns the new salon_address_id.'
        ),
        request=CreateSalonAddressSerializer,
        responses=SwaggerPage.response(description='Salon address added successfully'),
        tags=['Artists - Salon addresses'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateSalonAddressSerializer).validate
    def create_salon_address(request: Request) -> Response:
        return SalonAddressView().create_extract(params=request.params)

    @extend_schema(
        description=(
            'List your own active salon addresses, oldest first (at most 10). Each has salon_address_id, name, '
            'address lines, city, pin_code, latitude and longitude as numbers, and created_at. An empty list means '
            'none added yet.'
        ),
        parameters=GetSalonAddressesSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Data fetched successfully'),
        tags=['Artists - Salon addresses'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetSalonAddressesSerializer).validate
    def get_all_salon_addresses(request: Request) -> Response:
        return SalonAddressView().get_all_extract(params=request.params)

    @extend_schema(
        description=(
            'Edit one of your own active salon addresses. Send salon_address_id and only the fields to change; '
            'the rest are kept. Same rules as adding: name stays unique among your active addresses (ignoring case), '
            'coordinates in range and not both 0, more than six decimals rounded. address_line_2 can be cleared '
            'with null or "". An unknown, switched-off or other artist\'s address returns "Salon address not found".'
        ),
        request=UpdateSalonAddressSerializer,
        responses=SwaggerPage.response(description='Salon address updated successfully'),
        tags=['Artists - Salon addresses'],
    )
    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=UpdateSalonAddressSerializer).validate
    def update_salon_address(request: Request) -> Response:
        return SalonAddressView().update_extract(params=request.params)

    @extend_schema(
        description=(
            'Delete one of your own salon addresses. The address is switched off, not erased, so bookings that '
            'used it keep their history: it disappears from your list and from what customers see, and its name '
            'and one of your 10 slots become free again. An unknown, already deleted or other artist\'s address '
            'returns "Salon address not found".'
        ),
        parameters=DeleteSalonAddressSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Salon address deleted successfully'),
        tags=['Artists - Salon addresses'],
    )
    @api_view(['DELETE'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=DeleteSalonAddressSerializer).validate
    def delete_salon_address(request: Request) -> Response:
        return SalonAddressView().delete_extract(params=request.params)
