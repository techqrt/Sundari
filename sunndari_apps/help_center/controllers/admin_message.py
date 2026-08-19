from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.help_center.serializers.request.get.get_admin_messages import AdminGetMessagesSerializer
from sunndari_apps.help_center.serializers.request.create.create_admin_message import AdminCreateMessageSerializer
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportMessageResponseSerializer
from sunndari_apps.help_center.serializers.response.get_all.get_all_messages import SupportMessageResponseGetAllSerializer
from sunndari_apps.help_center.views.admin_message import AdminMessageView


class AdminMessageController:

    @extend_schema(
        description='List messages for a Help Center support conversation (admin-only, paginated).',
        parameters=AdminGetMessagesSerializer.get_parameters(),
        responses=SwaggerPage.response(response=SupportMessageResponseGetAllSerializer),
        tags=['Help Center Admin'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AdminGetMessagesSerializer).validate
    def get_all_messages(request: Request) -> Response:
        return AdminMessageView().get_all_extract(params=request.params)

    @extend_schema(
        description=(
            'Reply to a Help Center support conversation (admin-only). Automatically '
            "transitions the conversation from 'open' to 'running' on first reply."
        ),
        request=AdminCreateMessageSerializer,
        responses=SwaggerPage.response(response=SupportMessageResponseSerializer, description='Reply sent successfully'),
        tags=['Help Center Admin'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AdminCreateMessageSerializer).validate
    def create_message(request: Request) -> Response:
        return AdminMessageView().create_extract(params=request.params)
