from django.http import QueryDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request
from sunndari.constants import Constants
from sunndari_apps.common.utils import Utils


class SerializerValidations:
    def __init__(self, serializer, exec_func: str = ''):
        self.validation_error = Constants.validation_error
        self.serializer = serializer
        self.exec_func = exec_func

    @staticmethod
    def _copy_request_data(request_data):
        # QueryDict.copy() deep-copies, and an uploaded file larger than Django's in-memory
        # threshold (2.5 MB) is a TemporaryUploadedFile wrapping an open file handle, which
        # cannot be deep-copied — every such upload crashed here before validation ran.
        # Copy the key/value lists instead and keep the file objects as-is.
        if isinstance(request_data, QueryDict):
            data = QueryDict(mutable=True)
            for key, values in request_data.lists():
                data.setlist(key, list(values))
            return data
        return request_data.copy()

    def validate(self, func):
        def validator(*args, **kwargs):
            request: Request = args[0]

            if not hasattr(request.data, 'keys'):
                # A JSON array / string / number / null body: there are no fields to validate.
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data=Utils.error_response_data(message=Constants.validation_error, error=[Constants.request_body_not_object]),
                )
            data = self._copy_request_data(request.data)
            data.update(Utils.get_query_params(request=request))
            serializer = self.serializer(data=data)
            result = Utils().validator(serializer=serializer)
            if isinstance(result, bool):
                params = serializer.create(serializer.validated_data)
                request.params = params
                if request.method == 'GET':
                    request.params.present_url = request.build_absolute_uri()
                request.params.user_id = request.user.user_id

                return func(*args, **kwargs)
            return result

        return validator
