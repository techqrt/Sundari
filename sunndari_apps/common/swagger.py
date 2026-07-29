from drf_spectacular.utils import OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from sunndari.config import Configurations
from datetime import datetime


class SwaggerPage:

    @staticmethod
    def response(description: str = 'Success', response=None):
        return {200: OpenApiResponse(description=description, response=response)}

    @staticmethod
    def get_all_parameters():
        return [
            OpenApiParameter(name='value', description='Comma-separated column names to return',
                             required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='page_num', description='Page number',
                             required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='limit', description='Records per page',
                             required=False, type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
                             default=Configurations.pagination_count),
            OpenApiParameter(name='sort_by', description='Field to sort by',
                             required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='sort_order', description='asc or desc',
                             required=False, location=OpenApiParameter.QUERY,
                             type=str, enum=['asc', 'desc']),
            OpenApiParameter(name='filter_key', description='Field to filter by',
                             required=False, location=OpenApiParameter.QUERY, type=str),
            OpenApiParameter(name='filter_value', description='Value to filter with',
                             required=False, location=OpenApiParameter.QUERY, type=str),
            OpenApiParameter(name='search_key', description='Search keyword',
                             required=False, location=OpenApiParameter.QUERY, type=str),
            OpenApiParameter(name='from_date', description='Filter from date (DD-MM-YY)',
                             required=False, location=OpenApiParameter.QUERY, type=datetime),
            OpenApiParameter(name='to_date', description='Filter to date (DD-MM-YY)',
                             required=False, location=OpenApiParameter.QUERY, type=datetime),
        ]

    @staticmethod
    def get_parameters():
        return [
            OpenApiParameter(name='value', description='Comma-separated column names to return',
                             required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ]

    @staticmethod
    def search_parameters(key_description: str):
        return [
            OpenApiParameter(name='query', description=key_description, required=True, type=str),
        ]
