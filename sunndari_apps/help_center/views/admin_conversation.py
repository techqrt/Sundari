import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.help_center.services import SupportChatService
from sunndari_apps.help_center.utils import HelpCenterUtils
from sunndari_apps.help_center.models.conversation import SupportConversation
from sunndari_apps.help_center.dataclasses.request.get.get_admin_conversation import AdminGetConversationRequest
from sunndari_apps.help_center.dataclasses.request.get.get_admin_conversations import AdminGetConversationsRequest
from sunndari_apps.help_center.dataclasses.request.update.close_conversation import CloseConversationRequest
from sunndari_apps.help_center.serializers.response.get.get_conversation import SupportConversationResponseSerializer
from sunndari_apps.help_center.serializers.response.get_all.get_all_conversations import SupportConversationResponseGetAllSerializer
from sunndari.constants import Constants


class AdminConversationView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=SupportConversationResponseSerializer).exception_handler
    def get_extract(self, params: AdminGetConversationRequest):
        conversation = SupportChatService.get_conversation_for_admin(
            conversation_id=params.conversation_id, user_id=params.user_id,
        )
        utils = HelpCenterUtils(entity='conversation', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([conversation]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=SupportConversationResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: AdminGetConversationsRequest):
        SupportChatService.assert_admin(user_id=params.user_id)
        raw = SupportConversation.get_all(
            status=params.status, sort_by=params.sort_by, sort_order=params.sort_order, search_key=params.search_key,
        )
        pages = Paginator(raw, per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError(Constants.page_num_exceeded)
        page_data = list(pages.page(params.page_num))
        utils = HelpCenterUtils(entity='conversation')
        data = json.loads(utils.mapper(page_data))
        data = Utils.add_page_parameter(
            final_data=data,
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def close_extract(self, params: CloseConversationRequest):
        SupportChatService.close_conversation(conversation_id=params.conversation_id, admin_user_id=params.user_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Conversation closed successfully')
        )
