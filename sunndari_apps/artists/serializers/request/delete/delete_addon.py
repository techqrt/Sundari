from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari_apps.artists.dataclasses.request.delete.delete_addon import DeleteAddOnRequest


class DeleteAddOnSerializer(serializers.Serializer):
    addon_id = serializers.IntegerField()

    def create(self, validated_data) -> DeleteAddOnRequest:
        return DeleteAddOnRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='addon_id', description='ID of the add-on to delete',
            required=True, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        )]
