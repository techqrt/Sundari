from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari.config import Configurations
from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.customers.dataclasses.request.get.search_artist import SearchArtistRequest


class SearchArtistSerializer(serializers.Serializer):
    values = serializers.CharField(max_length=200, required=False, default='')
    page_num = serializers.IntegerField(default=1)
    limit = serializers.IntegerField(default=Configurations.pagination_count)
    sort_by = serializers.ChoiceField(choices=['rating', 'price', 'experience', 'name'], required=False, default='rating')
    sort_order = serializers.ChoiceField(choices=['asc', 'desc'], required=False, default='desc')
    search_key = serializers.CharField(max_length=100, required=False, default='')
    city = serializers.CharField(max_length=100, required=False, default='')
    category_id = serializers.IntegerField(required=False)
    sub_category_id = serializers.IntegerField(required=False)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    min_rating = serializers.DecimalField(max_digits=3, decimal_places=2, required=False)

    def create(self, validated_data) -> SearchArtistRequest:
        return SearchArtistRequest(**validated_data)

    @staticmethod
    def get_parameters() -> list:
        params = SwaggerPage.get_all_parameters()
        params.append(OpenApiParameter(
            name='city', description='Filter by artist city (partial match)',
            required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='category_id', description='Filter by service category',
            required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='sub_category_id', description='Filter by service sub-category (takes precedence over category_id)',
            required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='min_price', description='Minimum starting package price',
            required=False, type=OpenApiTypes.NUMBER, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='max_price', description='Maximum starting package price',
            required=False, type=OpenApiTypes.NUMBER, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='min_rating', description='Minimum average rating',
            required=False, type=OpenApiTypes.NUMBER, location=OpenApiParameter.QUERY,
        ))
        params.append(OpenApiParameter(
            name='sort_by', description='rating (default) / price / experience / name',
            required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY,
        ))
        return params
