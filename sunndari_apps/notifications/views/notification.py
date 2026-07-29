import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationsUtils
from sunndari_apps.notifications.dataclasses.request.get.get_notification import GetNotificationRequest
from sunndari_apps.notifications.dataclasses.request.update.mark_read import MarkReadRequest
from sunndari_apps.notifications.serializers.response.get.get_notification import NotificationResponseSerializer
from sunndari_apps.notifications.serializers.response.get_all.get_all_notification import NotificationResponseGetAllSerializer
from sunndari.constants import Constants


class NotificationView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=NotificationResponseSerializer).exception_handler
    def get_extract(self, params: GetNotificationRequest):
        notification = Notification.get(notification_id=params.notification_id)
        if not notification or notification['user_id'] != params.user_id:
            raise ValueError(Constants.item_not_found)
        utils = NotificationsUtils(entity='notification', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper([notification]))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=NotificationResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        reversed_mapped = NotificationsUtils.reverse_mapper('notification', [params.sort_by, params.filter_key])
        raw = Notification.get_all(
            user_id=params.user_id,
            sort_by=reversed_mapped.get(params.sort_by, ''),
            sort_order=params.sort_order,
            filter_key=reversed_mapped.get(params.filter_key, ''),
            filter_value=params.filter_value,
            search_key=params.search_key,
        )
        pages = Paginator(raw, per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = list(pages.page(params.page_num))
        utils = NotificationsUtils(entity='notification')
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
    def mark_read_extract(self, params: MarkReadRequest):
        notification = Notification.get(notification_id=params.notification_id)
        if not notification or notification['user_id'] != params.user_id:
            raise ValueError(Constants.item_not_found)
        Notification.mark_read(notification_id=params.notification_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Notification marked as read')
        )

    @Common().exception_handler
    def mark_all_read_extract(self, params):
        count = Notification.mark_all_read(user_id=params.user_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=f'{count} notification(s) marked as read')
        )
