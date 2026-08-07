from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.chat.serializers.request.get.get_conversation import GetConversationSerializer
from sunndari_apps.chat.serializers.response.get.get_conversation import ConversationResponseSerializer
from sunndari_apps.chat.views.conversation import ConversationView


class ConversationController:

    @extend_schema(
        description=(
            'Get (or lazily create) the conversation for a booking. Only the '
            "booking's customer or artist may access it, and only while the "
            'booking is confirmed or in progress.'
        ),
        parameters=GetConversationSerializer.get_parameters(),
        responses=SwaggerPage.response(response=ConversationResponseSerializer),
        tags=['Chat'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=GetConversationSerializer).validate
    def get_conversation(request: Request) -> Response:
        return ConversationView().get_extract(params=request.params)
