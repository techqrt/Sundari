import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.chat.services import ChatService
from sunndari_apps.chat.utils import ChatUtils
from sunndari_apps.chat.models.message import Message
from sunndari_apps.chat.dataclasses.request.get.get_messages import GetMessagesRequest
from sunndari_apps.chat.dataclasses.request.create.create_message import CreateMessageRequest
from sunndari_apps.chat.serializers.response.get.get_conversation import MessageResponseSerializer
from sunndari_apps.chat.serializers.response.get_all.get_all_messages import MessageResponseGetAllSerializer
from sunndari.constants import Constants


class MessageView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=MessageResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetMessagesRequest):
        conversation = ChatService.get_conversation_for_participant(
            booking_id=params.booking_id, user_id=params.user_id,
        )
        raw = Message.get_all(conversation_id=conversation['conversation_id'], sort_order=params.sort_order or 'asc')
        pages = Paginator(raw, per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError(Constants.page_num_exceeded)
        page_data = list(pages.page(params.page_num))
        utils = ChatUtils(entity='message')
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

    @Common(response_handler=MessageResponseSerializer).exception_handler
    def create_extract(self, params: CreateMessageRequest):
        message = ChatService.send_message(
            booking_id=params.booking_id, user_id=params.user_id, content=params.content,
        )
        utils = ChatUtils(entity='message')
        data = json.loads(utils.mapper([message]))[0]
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Message sent successfully', data=data)
        )
