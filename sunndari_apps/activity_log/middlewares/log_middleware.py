import threading

local = threading.local()


class LogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        local.__dict__.clear()
        local.ip_address = request.META.get('REMOTE_ADDR')
        local.user_agent = request.headers.get('User-Agent', '')
        local.end_point = request.path
        local.method = request.method
        return self.get_response(request)
