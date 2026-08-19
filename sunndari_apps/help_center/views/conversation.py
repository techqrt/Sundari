import json
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.help_center.services import SupportChatService
from sunndari_apps.help_center.utils import HelpCenterUtils
from sunndari_apps.help_center.dataclasses.request.get.get_conversation import GetConversationRequest
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportConversationResponseSerializer
from sunndari.constants import Constants


class ConversationView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=SupportConversationResponseSerializer).exception_handler
    def get_extract(self, params: GetConversationRequest):
        conversation = SupportChatService.get_conversation_for_customer(customer_id=params.user_id)
        utils = HelpCenterUtils(entity='conversation', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([conversation]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
