from pathlib import Path
from datetime import timedelta
import os
from sunndari.config import Configurations

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-change-this-in-production'

DEBUG = Configurations.debug

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',

    'sunndari_apps.authentication',
    'sunndari_apps.common',
    'sunndari_apps.activity_log',
    'sunndari_apps.helper_apis',
    'sunndari_apps.users',
    'sunndari_apps.core',
    'sunndari_apps.artists',
    'sunndari_apps.customers',
    'sunndari_apps.notifications',
    'sunndari_apps.admin_panel',
]

AUTH_USER_MODEL = 'auth.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

EXTERNAL_MIDDLEWARE = [
    'sunndari_apps.activity_log.middlewares.log_middleware.LogMiddleware',
]

MIDDLEWARE += EXTERNAL_MIDDLEWARE

ROOT_URLCONF = 'sunndari.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sunndari.wsgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': Configurations.db_name,
#         'USER': Configurations.db_user,
#         'PASSWORD': Configurations.db_password,
#         'HOST': Configurations.db_host,
#         'PORT': Configurations.db_port,
#     }
# }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'sunndari_apps.authentication.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=Configurations.jwt_expiry_days),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=Configurations.jwt_expiry_days),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'SUNNDARI API',
    'DESCRIPTION': 'Beauty Services Marketplace Platform',
    'VERSION': 'v1',
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = ['*']
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Celery
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULE = {
    'cancel-stale-pending-bookings': {
        'task': 'sunndari_apps.customers.tasks.cancel_stale_pending_bookings',
        'schedule': 60.0,
    },
    'send-appointment-reminders': {
        'task': 'sunndari_apps.notifications.tasks.send_appointment_reminders',
        'schedule': 600.0,
    },
}

# Brevo (email via SMTP)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp-relay.brevo.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = Configurations.brevo_smtp_login
EMAIL_HOST_PASSWORD = Configurations.brevo_smtp_key
DEFAULT_FROM_EMAIL = Configurations.default_from_email

# Google OAuth2
GOOGLE_CLIENT_ID = Configurations.google_client_id
