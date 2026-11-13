from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_salon_address import DeleteSalonAddressRequest


class DeleteSalonAddressSerializer(serializers.Serializer):
    salon_address_id = serializers.IntegerField()

    def create(self, validated_data) -> DeleteSalonAddressRequest:
        return DeleteSalonAddressRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='salon_address_id', description='ID of the salon address to delete',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
