from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class AuthRateThrottle(SimpleRateThrottle):
    """Strict limit per client IP for the public sign-in endpoints (OTP request / verify, login, register,
    password reset, token refresh). It caps how many SMS an attacker can trigger and how many passwords or
    codes they can try, across any number of phone numbers — the per-account cooldown and lockout cannot
    see that. The rate is read from settings on every request so a deployment (or a test) can change it."""
    scope = 'auth'

    def get_rate(self):
        return settings.AUTH_THROTTLE_RATE

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class UserRateThrottle(SimpleRateThrottle):
    """General ceiling on every other endpoint: per signed-in user (a shared office or carrier IP must not
    throttle many different customers together), falling back to the client IP for anonymous callers."""
    scope = 'user'

    def get_rate(self):
        return settings.USER_THROTTLE_RATE

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
