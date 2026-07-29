from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from sunndari_apps.artists.dataclasses.request.delete.remove_block import RemoveBlockRequest


class RemoveBlockSerializer(serializers.Serializer):
    block_date = serializers.DateField(input_formats=['%Y-%m-%d', '%d-%m-%Y'])

    def create(self, validated_data) -> RemoveBlockRequest:
        return RemoveBlockRequest(block_date=str(validated_data['block_date']))

    @staticmethod
    def get_parameters() -> list:
        return [OpenApiParameter(
            name='block_date', description='Date to unblock (YYYY-MM-DD)',
            required=True, type=str, location=OpenApiParameter.QUERY,
        )]
