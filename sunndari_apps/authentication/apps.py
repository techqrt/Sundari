from django.apps import AppConfig
class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sunndari_apps.authentication'

    def ready(self):
        from sunndari_apps.authentication import schema  # noqa: F401  (registers the JWT scheme with the API docs)
