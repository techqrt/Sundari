from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.chat.serializers.request.get.get_messages import GetMessagesSerializer
from sunndari_apps.chat.serializers.request.create.create_message import CreateMessageSerializer
from sunndari_apps.chat.serializers.response.get.get_conversation import MessageResponseSerializer
from sunndari_apps.chat.serializers.response.get_all.get_all_messages import MessageResponseGetAllSerializer
from sunndari_apps.chat.views.message import MessageView


class MessageController:

    @extend_schema(
        description='List messages for a booking conversation (participant-only, paginated).',
        parameters=GetMessagesSerializer.get_parameters(),
        responses=SwaggerPage.response(response=MessageResponseGetAllSerializer),
        tags=['Chat'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetMessagesSerializer).validate
    def get_all_messages(request: Request) -> Response:
        return MessageView().get_all_extract(params=request.params)

    @extend_schema(
        description=(
            'Send a message on a booking conversation. Only accepted while the '
            'booking is confirmed or in progress.'
        ),
        request=CreateMessageSerializer,
        responses=SwaggerPage.response(response=MessageResponseSerializer, description='Message sent successfully'),
        tags=['Chat'],
    )
    @api_view(['POST'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=CreateMessageSerializer).validate
    def create_message(request: Request) -> Response:
        return MessageView().create_extract(params=request.params)
