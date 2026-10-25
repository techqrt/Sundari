from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Tells the generated API docs (/docs/, /redoc/) how the custom JWTAuthentication class works, so every
    protected endpoint is documented as requiring `Authorization: Bearer <access token>`."""
    target_class = 'sunndari_apps.authentication.authentication.JWTAuthentication'
    name = 'bearerAuth'

    def get_security_definition(self, auto_schema):
        return {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}
