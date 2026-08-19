from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.help_center.serializers.request.get.get_messages import SupportGetMessagesSerializer
from sunndari_apps.help_center.serializers.request.create.create_message import SupportCreateMessageSerializer
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportMessageResponseSerializer
from sunndari_apps.help_center.serializers.response.get_all.get_all_messages import SupportMessageResponseGetAllSerializer
from sunndari_apps.help_center.views.message import MessageView


class MessageController:

    @extend_schema(
        description='List messages for the authenticated customer\'s support conversation (paginated).',
        parameters=SupportGetMessagesSerializer.get_parameters(),
        responses=SwaggerPage.response(response=SupportMessageResponseGetAllSerializer),
        tags=['Help Center'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SupportGetMessagesSerializer).validate
    def get_all_messages(request: Request) -> Response:
        return MessageView().get_all_extract(params=request.params)

    @extend_schema(
        description=(
            'Send a Help Center message. Lazily starts a new support conversation if the '
            "customer doesn't currently have an open one."
        ),
        request=SupportCreateMessageSerializer,
        responses=SwaggerPage.response(response=SupportMessageResponseSerializer, description='Message sent successfully'),
        tags=['Help Center'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SupportCreateMessageSerializer).validate
    def create_message(request: Request) -> Response:
        return MessageView().create_extract(params=request.params)
