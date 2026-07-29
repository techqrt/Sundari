import random
from urllib.parse import urlsplit, unquote_plus
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from sunndari.config import Configurations
from sunndari.constants import Constants
from typing import Union


class Utils:
    def __init__(self):
        super().__init__()
        self.validation_error = Constants.validation_error

    @staticmethod
    def success_response_data(message: str, data: Union[list, dict] = None, image: bool = False):
        if image:
            return message
        if data is None and message is None:
            return {'status': True}
        if message is None:
            return {'status': True, 'data': data}
        if data is None:
            return {'status': True, 'message': message}
        return {'status': True, 'message': message, 'data': data}

    @staticmethod
    def error_response_data(message: str, error: list):
        return {'status': False, 'message': message, 'error': error}

    @staticmethod
    def env_exception_handler(message: str):
        if Configurations.debug:
            return message
        return Constants.server_error

    @staticmethod
    def add_page_parameter(
        final_data: list,
        page_num: int,
        total_page: int,
        present_url: str,
        next_page_required: bool = False,
    ):
        to_return = {
            'data': final_data,
            'presentPage': page_num,
            'totalPage': total_page,
        }

        if total_page > 1:
            if 'page_num' in present_url:
                base_next_url = present_url
            else:
                if '?' in present_url:
                    base_next_url = present_url + '&page_num=' + str(page_num)
                else:
                    base_next_url = present_url + '?page_num=' + str(page_num)

            if next_page_required and page_num < total_page:
                to_return['nextPageUrl'] = base_next_url.replace(
                    f'page_num={page_num}', f'page_num={page_num + 1}'
                )

            if page_num > 1:
                to_return['previousPageUrl'] = base_next_url.replace(
                    f'page_num={page_num}', f'page_num={page_num - 1}'
                )

        return to_return

    @staticmethod
    def extract_params(url: str):
        split_url = urlsplit(url)
        info = split_url.query if split_url.query else 'page_num=1'
        return info.split('&'), split_url.path

    @staticmethod
    def get_query_params(request: Request):
        query_params = {}
        try:
            url = request.get_full_path()
        except Exception:
            url = request.path
        query, base_url = Utils.extract_params(url=url)
        for i in query:
            if '=' in i:
                key, value = i.split('=', 1)
            else:
                key, value = i, ''
            query_params[unquote_plus(key)] = unquote_plus(value)
        return query_params

    def validator(self, serializer):
        if serializer.is_valid() is False:
            response_data = Utils.error_response_data(
                message=self.validation_error, error=[serializer.errors]
            )
            return Response(response_data, status.HTTP_400_BAD_REQUEST)
        return True

    @staticmethod
    def generate_otp(length: int = 6):
        if length < 4:
            raise ValueError('OTP length should be at least 4.')
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
