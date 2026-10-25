"""The settings module is evaluated once at import, so each case runs in a fresh interpreter with the
environment under test. A deployment with DEBUG off must refuse to boot on a weak configuration."""
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent
GOOD = {
    'DEBUG': 'False',
    'SECRET_KEY': 'k' * 12 + 'unique-random-value-0123456789-abcdefghij-ABCDEFGHIJ',
    'FIELD_ENCRYPTION_KEY': 'ZmFrZS1mZXJuZXQta2V5LWZvci10ZXN0cy0wMTIzNDU2Nzg=',
    'ALLOWED_HOSTS': 'api.example.com',
    'THROTTLE_NUM_PROXIES': '1',
    'CORS_ALLOWED_ORIGINS': 'https://admin.example.com',
}
PROBE = (
    "import os, sys; sys.path.insert(0, os.getcwd()); import django; os.environ['DJANGO_SETTINGS_MODULE']='sunndari.settings'; django.setup();"
    "from django.conf import settings as s; print('OK', s.ALLOWED_HOSTS, s.CORS_ALLOW_ALL_ORIGINS, s.SECURE_SSL_REDIRECT,"
    " s.SESSION_COOKIE_SECURE, s.SECURE_HSTS_SECONDS, getattr(s, 'CORS_ALLOWED_ORIGINS', None))"
)


def boot(**overrides):
    env = {**os.environ, **GOOD, **overrides}
    for key in [k for k, v in overrides.items() if v is None]:
        env.pop(key, None)
    result = subprocess.run([sys.executable, '-I', '-c', PROBE], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=120)
    return result.returncode, result.stdout + result.stderr


class ProductionSettingsTest(SimpleTestCase):

    def test_a_properly_configured_deployment_boots_with_the_hardening_on(self):
        code, out = boot()
        self.assertEqual(code, 0, out)
        self.assertIn("OK ['api.example.com'] False True True 31536000 ['https://admin.example.com']", out)

    def test_refuses_to_boot_with_the_public_default_secret_key(self):
        code, out = boot(SECRET_KEY=None)
        self.assertNotEqual(code, 0)
        self.assertIn('SECRET_KEY must be set', out)

    def test_refuses_a_short_or_django_insecure_secret_key(self):
        for weak in ('short', 'django-insecure-' + 'x' * 60):
            code, out = boot(SECRET_KEY=weak)
            self.assertNotEqual(code, 0, weak)
            self.assertIn('SECRET_KEY must be set', out)

    def test_refuses_to_boot_without_a_separate_encryption_key(self):
        code, out = boot(FIELD_ENCRYPTION_KEY='')
        self.assertNotEqual(code, 0)
        self.assertIn('FIELD_ENCRYPTION_KEY must be set', out)

    def test_refuses_to_boot_without_explicit_allowed_hosts(self):
        code, out = boot(ALLOWED_HOSTS='')
        self.assertNotEqual(code, 0)
        self.assertIn('ALLOWED_HOSTS', out)

    def test_refuses_to_boot_without_the_proxy_count_for_rate_limiting(self):
        code, out = boot(THROTTLE_NUM_PROXIES='')
        self.assertNotEqual(code, 0)
        self.assertIn('THROTTLE_NUM_PROXIES', out)

    def test_debug_on_keeps_the_developer_defaults(self):
        code, out = boot(DEBUG='True', SECRET_KEY=None, FIELD_ENCRYPTION_KEY='', ALLOWED_HOSTS='', CORS_ALLOWED_ORIGINS='')
        self.assertEqual(code, 0, out)
        self.assertIn("OK ['*'] True", out)
