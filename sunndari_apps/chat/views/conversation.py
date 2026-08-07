import json
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.chat.services import ChatService
from sunndari_apps.chat.utils import ChatUtils
from sunndari_apps.chat.dataclasses.request.get.get_conversation import GetConversationRequest
from sunndari_apps.chat.serializers.response.get.get_conversation import ConversationResponseSerializer
from sunndari.constants import Constants


class ConversationView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=ConversationResponseSerializer).exception_handler
    def get_extract(self, params: GetConversationRequest):
        conversation = ChatService.get_or_create_conversation(
            booking_id=params.booking_id, user_id=params.user_id,
        )
        conversation = dict(conversation)
        conversation['is_open'] = ChatService.is_open(
            booking=ChatService.get_booking_or_raise(booking_id=params.booking_id),
        )
        utils = ChatUtils(entity='conversation', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([conversation]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
