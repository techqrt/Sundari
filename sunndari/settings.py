from pathlib import Path
from datetime import timedelta
import os
import sys
from decouple import config
from sunndari.config import Configurations

BASE_DIR = Path(__file__).resolve().parent.parent

# Also the JWT signing key. Set SECRET_KEY in the environment for any real deployment; the
# fallback is the previous hard-coded value so existing local setups keep working, but it is
# public (it is in git history) and must never be used in production.
INSECURE_DEV_SECRET_KEY = 'django-insecure-change-this-in-production'
SECRET_KEY = config('SECRET_KEY', default=INSECURE_DEV_SECRET_KEY)

DEBUG = Configurations.debug

# True under `manage.py test` / pytest — guards external side effects (Firebase
# writes, etc.) that must never fire against real third-party services from
# the test suite, since Django's transaction rollback only protects the DB.
TESTING = 'test' in sys.argv or 'pytest' in sys.modules

# Anything that is neither a developer's machine (DEBUG on) nor the test runner. These deployments refuse to
# start on a weak configuration instead of running with it quietly (see the checks below).
PRODUCTION = not DEBUG and not TESTING


def _csv(name: str) -> list:
    return [item.strip() for item in config(name, default='').split(',') if item.strip()]


if PRODUCTION:
    from django.core.exceptions import ImproperlyConfigured
    if SECRET_KEY == INSECURE_DEV_SECRET_KEY or SECRET_KEY.startswith('django-insecure') or len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            'SECRET_KEY must be set to a unique random value of at least 50 characters when DEBUG is off '
            '(it signs every login token). Generate one with: python -c "from django.core.management.utils '
            'import get_random_secret_key as k; print(k())"'
        )
    if not config('FIELD_ENCRYPTION_KEY', default=''):
        raise ImproperlyConfigured(
            'FIELD_ENCRYPTION_KEY must be set when DEBUG is off, separately from SECRET_KEY, so that rotating '
            'SECRET_KEY can never make encrypted ID numbers and bank details unreadable. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    if not _csv('ALLOWED_HOSTS'):
        raise ImproperlyConfigured('ALLOWED_HOSTS (comma-separated hostnames) must be set when DEBUG is off.')
    if not config('THROTTLE_NUM_PROXIES', default=''):
        raise ImproperlyConfigured(
            'THROTTLE_NUM_PROXIES must be set when DEBUG is off: the number of reverse proxies / load balancers in '
            'front of the app (0 if clients connect directly). Rate limiting identifies clients by IP, and a wrong '
            'value either lets an attacker dodge the limit with a forged X-Forwarded-For header or puts every user '
            'in one shared bucket behind the proxy.'
        )

# Developers keep the permissive default; a real deployment lists its hostnames explicitly.
ALLOWED_HOSTS = _csv('ALLOWED_HOSTS') or ['*']

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',

    # Must precede 'django.contrib.staticfiles' — 'daphne' overrides the
    # `runserver` command to serve ASGI (HTTP + WebSocket) instead of plain
    # WSGI, and Django only applies that override for apps listed earlier.
    'daphne',
    'channels',

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
    'sunndari_apps.chat',
    'sunndari_apps.help_center',
    'sunndari_apps.payments',
    'sunndari_apps.wallet',
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
ASGI_APPLICATION = 'sunndari.asgi.application'

# Chat realtime channel layer — same Redis instance as Celery, separate logical DB.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': ['redis://localhost:6379/1'],
        },
    },
}

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
# Fernet key for encrypting sensitive fields (ID numbers). Falls back to a SECRET_KEY-derived key.
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')
# Never served by URL — KYC documents live here (see common/storage.PrivateMediaStorage).
PRIVATE_MEDIA_ROOT = os.path.join(BASE_DIR, 'private_media')

if TESTING:
    # Uploads made by the test suite must not land in the real media folders.
    import tempfile
    MEDIA_ROOT = tempfile.mkdtemp(prefix='sunndari_test_media_')
    PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix='sunndari_test_private_media_')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

UNFOLD = {
    "SITE_TITLE": "SUNNDARI Admin",
    "SITE_HEADER": "SUNNDARI",
}

# Request rate limits (see common/throttles.py). The test runner gets limits no test will reach; the
# throttling tests set their own.
AUTH_THROTTLE_RATE = '100000/min' if TESTING else config('AUTH_THROTTLE_RATE', default='30/min')
USER_THROTTLE_RATE = '100000/min' if TESTING else config('USER_THROTTLE_RATE', default='300/min')

# Throttle counters must be shared by every worker process, so a real deployment keeps them in Redis (already
# required for Celery); a developer's machine and the tests use the in-process cache.
if PRODUCTION:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://localhost:6379/1'),
    }}
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'sunndari_apps.authentication.authentication.JWTAuthentication',
    ),
    'DEFAULT_THROTTLE_CLASSES': ('sunndari_apps.common.throttles.UserRateThrottle',),
    # How many proxies sit in front of the app, so the real client IP is read from X-Forwarded-For instead of
    # trusting the whole (forgeable) header. 0 = clients connect directly (a developer's machine).
    'NUM_PROXIES': int(config('THROTTLE_NUM_PROXIES', default='0') or 0),
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
    'ENUM_NAME_OVERRIDES': {
        'ReviewDecisionEnum': 'sunndari.constants.REVIEW_DECISION_CHOICES',
        'RescheduleDecisionEnum': 'sunndari.constants.RESCHEDULE_DECISION_CHOICES',
    },
}

# The mobile apps are not browsers and need no CORS; only web clients (the admin dashboard) do. Open to every
# origin on a developer's machine, restricted to the CORS_ALLOWED_ORIGINS list in a real deployment.
CORS_ALLOW_ALL_ORIGINS = not PRODUCTION
CORS_ALLOWED_ORIGINS = _csv('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_HEADERS = ['*']
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if PRODUCTION:
    # Transport security for a deployment behind HTTPS (Django deployment checklist): redirect to HTTPS, tell
    # browsers to insist on it, and keep session / CSRF cookies off plain HTTP.
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

# Celery
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
if TESTING:
    # Queued tasks go to an in-process queue, so the test suite never needs (or waits for) Redis.
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'
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
    'mark-missed-bookings': {
        'task': 'sunndari_apps.customers.tasks.mark_missed_bookings',
        'schedule': 300.0,
    },
    'redispatch-service-notifications': {
        'task': 'sunndari_apps.core.tasks.redispatch_unnotified_service_activations',
        'schedule': 600.0,
    },
    'retry-owed-refunds': {
        'task': 'sunndari_apps.payments.tasks.retry_owed_refunds',
        # Each payment backs off on its own (1m, 2m, 4m ... capped); this is just how often the queue is looked at.
        'schedule': 300.0,
    },
    'reconcile-pending-payments': {
        'task': 'sunndari_apps.payments.tasks.reconcile_pending_payments',
        'schedule': 600.0,
    },
    'expire-lapsed-coins': {
        'task': 'sunndari_apps.wallet.tasks.expire_lapsed_coins',
        # Coin batches expire on ~1-year windows, unlike the minute-scale booking-lock
        # sweeps above — once/day is plenty.
        'schedule': 86400.0,
    },
}

# Brevo (email via SMTP). The login and key come from the environment, never from code. The defaults are Brevo's
# relay; set EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend to print emails instead of sending them
# (the test runner already swaps in an in-memory backend).
EMAIL_BACKEND = config('EMAIL_BACKEND', default='sunndari_apps.common.emailing.CertifiSMTPEmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp-relay.brevo.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
# Without a timeout Django waits forever on a stalled mail server, which would hang the request that sent the email.
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)
EMAIL_HOST_USER = Configurations.brevo_smtp_login
EMAIL_HOST_PASSWORD = Configurations.brevo_smtp_key
DEFAULT_FROM_EMAIL = Configurations.default_from_email

# Google OAuth2
GOOGLE_CLIENT_ID = Configurations.google_client_id
