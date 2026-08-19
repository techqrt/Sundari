from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from sunndari_apps.common.swagger import SwaggerPage
from sunndari_apps.common.serializer_validations import SerializerValidations
from sunndari_apps.help_center.serializers.request.get.get_conversation import SupportGetConversationSerializer
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportConversationResponseSerializer
from sunndari_apps.help_center.views.conversation import ConversationView


class ConversationController:

    @extend_schema(
        description=(
            "Get the authenticated customer's current Help Center support conversation "
            '(the most recent non-closed one, if any).'
        ),
        parameters=SupportGetConversationSerializer.get_parameters(),
        responses=SwaggerPage.response(response=SupportConversationResponseSerializer),
        tags=['Help Center'],
    )
    @api_view(['GET'])
    @permission_classes([IsAuthenticated])
    @SerializerValidations(serializer=SupportGetConversationSerializer).validate
    def get_conversation(request: Request) -> Response:
        return ConversationView().get_extract(params=request.params)
