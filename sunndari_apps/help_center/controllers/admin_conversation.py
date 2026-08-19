from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.help_center.serializers.request.get.get_admin_conversation import AdminGetConversationSerializer
from sunndari_apps.help_center.serializers.request.get.get_admin_conversations import AdminGetConversationsSerializer
from sunndari_apps.help_center.serializers.request.update.close_conversation import CloseConversationSerializer
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportConversationResponseSerializer
from sunndari_apps.help_center.serializers.response.get_all.get_all_conversations import SupportConversationResponseGetAllSerializer
from sunndari_apps.help_center.views.admin_conversation import AdminConversationView


class AdminConversationController:

    @extend_schema(
        description=(
            'List Help Center support conversations (admin-only), filterable by status '
            '(open / running / closed) and paginated.'
        ),
        parameters=AdminGetConversationsSerializer.get_parameters(),
        responses=SwaggerPage.response(response=SupportConversationResponseGetAllSerializer),
        tags=['Help Center Admin'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AdminGetConversationsSerializer).validate
    def get_all_conversations(request: Request) -> Response:
        return AdminConversationView().get_all_extract(params=request.params)

    @extend_schema(
        description='Get a single Help Center support conversation (admin-only).',
        parameters=AdminGetConversationSerializer.get_parameters(),
        responses=SwaggerPage.response(response=SupportConversationResponseSerializer),
        tags=['Help Center Admin'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=AdminGetConversationSerializer).validate
    def get_conversation(request: Request) -> Response:
        return AdminConversationView().get_extract(params=request.params)

    @extend_schema(
        description=(
            'Close a Help Center support conversation (admin-only). Once closed, the '
            'customer can no longer send messages on it and must start a new conversation.'
        ),
        parameters=CloseConversationSerializer.get_parameters(),
        responses=SwaggerPage.response(description='Conversation closed successfully'),
        tags=['Help Center Admin'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CloseConversationSerializer).validate
    def close_conversation(request: Request) -> Response:
        return AdminConversationView().close_extract(params=request.params)
