"""QA harness for the full-flow regression run.

Unlike the project's unit tests, a failed check here does NOT abort: every check is recorded
(PASS / FAIL / BLOCKED / UNVERIFIED / OBSERVATION) with expected-vs-actual evidence and a severity,
and the whole run is dumped to JSON for the report. Nothing in the application is modified; all data
lives in Django's throw-away test database and temp media directories.
"""
import contextlib
import io
import json
import logging
import os
import sys
from datetime import timedelta, date
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token, generate_refresh_token

RESULTS: list = []
ENDPOINTS: dict = {}          # (METHOD, path) -> set of HTTP statuses observed
OUT_PATH = os.environ.get('QA_OUT', '/tmp/qa_results.json')


def record(flow, name, ok, expected, actual, sev='P2', note=''):
    RESULTS.append({'flow': flow, 'name': name, 'result': 'PASS' if ok else 'FAIL', 'expected': str(expected)[:300],
                    'actual': str(actual)[:400], 'severity': '' if ok else sev, 'note': note})
    return ok


def blocked(flow, name, why):
    RESULTS.append({'flow': flow, 'name': name, 'result': 'BLOCKED', 'expected': '', 'actual': why, 'severity': '', 'note': ''})


def unverified(flow, name, why, sev='P2'):
    RESULTS.append({'flow': flow, 'name': name, 'result': 'UNVERIFIED', 'expected': '', 'actual': why, 'severity': sev, 'note': ''})


def observe(flow, name, actual, sev='P3', note=''):
    RESULTS.append({'flow': flow, 'name': name, 'result': 'OBSERVATION', 'expected': '', 'actual': str(actual)[:400], 'severity': sev, 'note': note})


def dump():
    with open(OUT_PATH, 'w') as handle:
        json.dump(RESULTS, handle, indent=1, default=str)
    with open(OUT_PATH.replace('.json', '_endpoints.json'), 'w') as handle:
        json.dump({f'{m} {p}': sorted(v) for (m, p), v in ENDPOINTS.items()}, handle, indent=1)


# ---- capture everything printed/logged during the run, to audit for leaked secrets afterwards
class _Tee(io.StringIO):
    def __init__(self, original):
        super().__init__()
        self._original = original

    def write(self, text):
        self._original.write(text)
        return super().write(text)


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record_):
        try:
            self.lines.append(self.format(record_))
        except Exception:
            pass


CAPTURED_STDOUT = _Tee(sys.stdout)
sys.stdout = CAPTURED_STDOUT
LOG_CAPTURE = _LogCapture()
LOG_CAPTURE.setFormatter(logging.Formatter('%(name)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(LOG_CAPTURE)


class Actor:
    def __init__(self, user, token, refresh):
        self.user, self.token, self.refresh = user, token, refresh
        self.client = new_client(token)

    @property
    def id(self):
        return self.user.user_id


def new_client(token=None):
    client = APIClient()
    client.raise_request_exception = False        # a crash must surface as a 500 we can record
    if token:
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def make_actor(role, phone, name=None, email=None, password=None):
    user = User.objects.create(phone_number=phone, email=email, role=role, name=name or f'QA {role} {phone[-4:]}')
    if password:
        user.set_password(password)
    token, refresh = generate_jwt_token(user), generate_refresh_token(user)
    user.access_token, user.refresh_token = token, refresh
    user.save()
    return Actor(user, token, refresh)


def body(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def data(resp):
    return body(resp).get('data')


def is_2xx(resp):
    return 200 <= resp.status_code < 300


@contextlib.contextmanager
def at(moment):
    """Time travel: every timezone.now() call inside the block returns `moment`."""
    with patch('django.utils.timezone.now', return_value=moment):
        yield


def future_date(days=3):
    return date.today() + timedelta(days=days)


def fmt_date(d):
    return d.strftime('%d-%m-%y')


# ---- record every (method, path) the QA run really sends, with the statuses it got back
from django.test import client as _dj_client

_original_request = _dj_client.Client.request


def _tracked_request(self, **request):
    response = _original_request(self, **request)
    ENDPOINTS.setdefault((request.get('REQUEST_METHOD', '?'), request.get('PATH_INFO', '?')), set()).add(response.status_code)
    return response


_dj_client.Client.request = _tracked_request
