from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.views.public_profile import PublicArtistView
from sunndari.constants import Constants


class PublicArtistSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=80)


class PublicArtistController:

    @extend_schema(
        description='Public (no login) artist page for a shared link: approved artists only, minimal public fields.',
        parameters=[OpenApiParameter(name='slug', required=True, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY)],
        responses=SwaggerPage.response(description='Public artist profile'),
        tags=['Public'],
    )
    @api_view(['GET'])
    @authentication_classes([])
    @permission_classes([AllowAny])
    def get_public_artist(request: Request) -> Response:
        # No SerializerValidations here: that decorator reads request.user, and this
        # endpoint is intentionally anonymous (a stray/expired Authorization header is ignored).
        serializer = PublicArtistSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                status=400,
                data=Utils.error_response_data(message=Constants.validation_error, error=[serializer.errors]),
            )
        return PublicArtistView().get_extract(
            slug=serializer.validated_data['slug'], present_url=request.build_absolute_uri(),
        )
