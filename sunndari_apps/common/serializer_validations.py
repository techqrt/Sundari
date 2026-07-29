from rest_framework.request import Request
from sunndari.constants import Constants
from sunndari_apps.common.utils import Utils


class SerializerValidations:
    def __init__(self, serializer, exec_func: str = ''):
        self.validation_error = Constants.validation_error
        self.serializer = serializer
        self.exec_func = exec_func

    def validate(self, func):
        def validator(*args, **kwargs):
            request: Request = args[0]

            data = request.data.copy()
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
