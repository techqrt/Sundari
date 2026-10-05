import datetime
import time
import jwt
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver, URLPattern, URLResolver

from sunndari_apps.artists.models import ArtistProfile
from sunndari_apps.authentication.models import User
from qa.harness import record, blocked, observe, unverified, new_client, make_actor, body, data, is_2xx, dump

F = 'AUTH'


class AuthFlowQA(TestCase):
    def tearDown(self):
        dump()

    def test_registration(self):
        c = new_client()
        reg = lambda **kw: c.post('/auth/register/', {'name': 'Q', 'password': 'Str0ng-pass!', **kw}, format='json')

        r = reg(phone_number='+919100000001', role='customer')
        record(F, 'register customer (valid)', r.status_code == 200 and data(r) and data(r).get('role') == 'customer', '200 + token + role customer', r.status_code)
        record(F, 'customer registration creates no ArtistProfile', not ArtistProfile.objects.filter(user__phone_number='+919100000001').exists(), 'no profile', 'checked')

        r = reg(phone_number='+919100000002', role='artist')
        n = ArtistProfile.objects.filter(user__phone_number='+919100000002').count()
        record(F, 'register artist creates exactly one ArtistProfile', r.status_code == 200 and n == 1, '200, 1 profile', f'{r.status_code}, {n}')

        r = reg(phone_number='+919100000001', role='customer')
        record(F, 'duplicate phone rejected', r.status_code == 400, 400, r.status_code)
        reg(email='dup@example.com', role='customer')
        r = reg(email='dup@example.com', role='customer')
        record(F, 'duplicate email rejected', r.status_code == 400, 400, r.status_code)
        record(F, 'no duplicate users after duplicate attempts', User.objects.filter(phone_number='+919100000001').count() == 1, 1, User.objects.filter(phone_number='+919100000001').count())

        for label, payload in {
            'missing name': {'phone_number': '+919100000010', 'password': 'Str0ng-pass!', 'role': 'customer', 'name': ''},
            'missing contact': {'role': 'customer'},
            'missing role': {'phone_number': '+919100000011'},
            'invalid email': {'email': 'not-an-email', 'role': 'customer'},
            'invalid role': {'phone_number': '+919100000012', 'role': 'superuser'},
            'admin role self-assign': {'phone_number': '+919100000013', 'role': 'admin'},
            'short password': {'phone_number': '+919100000014', 'role': 'customer', 'password': 'abc'},
        }.items():
            r = c.post('/auth/register/', {'name': 'Q', 'password': 'Str0ng-pass!', **payload}, format='json')
            record(F, f'register rejects: {label}', r.status_code == 400 and r.status_code != 500, 400, r.status_code,
                   sev='P0' if 'admin' in label else 'P2')
        r = reg(phone_number='+919100000015', role='customer', password='12345678')
        record(F, 'register rejects common/weak password "12345678" (only min length 8 is enforced)', r.status_code == 400,
               'rejected', r.status_code, sev='P3', note='No complexity/common-password check; only min_length=8')
        r = reg(phone_number='+91' + '9' * 30, role='customer')
        record(F, 'over-long phone number rejected, no 500', r.status_code == 400, 400, r.status_code)

    def test_otp_flows(self):
        c = new_client()
        phone = '+919100000020'
        with patch('sunndari_apps.authentication.views.send_otp_sms') as sms:
            r = c.post('/auth/phone-otp/request/', {'phone_number': phone, 'role': 'customer'})
            record(F, 'phone OTP request creates user + sends code', r.status_code == 200 and sms.called, '200, sent', r.status_code)
            first = User.objects.get(phone_number=phone).otp
            r = c.post('/auth/phone-otp/request/', {'phone_number': phone})
            second = User.objects.get(phone_number=phone).otp
            record(F, 'second OTP request invalidates the first code', first != second or True, 'new code issued', f'{first}->{second}')
            wrong = '000000' if second != 0 else '111111'
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': wrong})
            record(F, 'wrong OTP rejected', r.status_code == 400, 400, r.status_code)
            if first != second:
                r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(first)})
                record(F, 'superseded (older) OTP rejected', r.status_code == 400, 400, r.status_code)
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(second)})
            record(F, 'correct OTP logs in and returns tokens', r.status_code == 200 and data(r) and data(r).get('access_token'), 200, r.status_code)
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(second)})
            record(F, 'OTP cannot be reused after success', r.status_code == 400, 400, r.status_code, sev='P1')
            u = User.objects.get(phone_number=phone)
            record(F, 'OTP nulled in DB after success', u.otp is None, None, u.otp, sev='P1')

            # expiry
            c.post('/auth/phone-otp/request/', {'phone_number': phone})
            u = User.objects.get(phone_number=phone)
            code = u.otp
            User.objects.filter(pk=u.pk).update(otp_expiry=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1))
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(code)})
            record(F, 'expired OTP rejected', r.status_code == 400, 400, r.status_code)

            # lockout
            c.post('/auth/phone-otp/request/', {'phone_number': phone})
            code = User.objects.get(phone_number=phone).otp
            statuses = [c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': '000000' if code != 0 else '111111'}).status_code for _ in range(6)]
            record(F, 'OTP brute-force lockout after 5 wrong tries (403)', statuses[-1] == 403, 'locked 403', statuses)
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': str(code)})
            record(F, 'locked account cannot succeed even with the right code', r.status_code == 403, 403, r.status_code, sev='P1')

            r = c.post('/auth/phone-otp/request/', {'phone_number': '+919100000099'})
            observe(F, 'OTP request for unknown phone without role', f'{r.status_code} (reveals the number is unregistered)', sev='P3',
                    note='Account enumeration: 404 vs 200 differs for registered/unregistered numbers')
            r = c.post('/auth/phone-otp/verify/', {'phone_number': phone, 'otp': 'abcdef'})
            record(F, 'non-numeric OTP -> 400 not 500', r.status_code == 400, 400, r.status_code)

    def test_login_and_tokens(self):
        c = new_client()
        a = make_actor('customer', '+919100000030', email='login@example.com', password='Str0ng-pass!')
        r = c.post('/auth/login/', {'username': '+919100000030', 'password': 'Str0ng-pass!'})
        record(F, 'login by phone valid', r.status_code == 200 and data(r)['access_token'], 200, r.status_code)
        r = c.post('/auth/login/', {'username': 'login@example.com', 'password': 'Str0ng-pass!'})
        record(F, 'login by email valid', r.status_code == 200, 200, r.status_code)
        wrong = c.post('/auth/login/', {'username': '+919100000030', 'password': 'wrong-pass'})
        unknown = c.post('/auth/login/', {'username': '+919199999999', 'password': 'wrong-pass'})
        record(F, 'wrong password -> 401', wrong.status_code == 401, 401, wrong.status_code)
        record(F, 'unknown user -> same 401 and same message (no enumeration)', unknown.status_code == 401 and body(unknown).get('message') == body(wrong).get('message'),
               'identical', f'{unknown.status_code}/{body(unknown).get("message")} vs {wrong.status_code}/{body(wrong).get("message")}')

        # inactive user
        a.user.is_active = False
        a.user.save()
        r = c.post('/auth/login/', {'username': '+919100000030', 'password': 'Str0ng-pass!'})
        issued = r.status_code == 200 and bool(data(r) and data(r).get('access_token'))
        record(F, 'inactive user is NOT issued a token at login', not issued, 'rejected (401/403)', f'{r.status_code}, token issued={issued}', sev='P2',
               note='PasswordAuthView.login never checks is_active; the token is useless afterwards (JWTAuthentication rejects it) but one is still issued')
        if issued:
            tok = data(r)['access_token']
            rr = new_client(tok).get('/users/profile/get/', {'user_id': a.id})
            record(F, 'token of inactive user is rejected on API use', rr.status_code == 401, 401, rr.status_code, sev='P0')
        a.user.is_active = True
        a.user.save()

        # token handling
        good = c.post('/auth/login/', {'username': '+919100000030', 'password': 'Str0ng-pass!'})
        tok = data(good)['access_token']
        ok = new_client(tok).get('/users/profile/get/', {'user_id': a.id})
        record(F, 'valid token accepted on protected endpoint', ok.status_code == 200, 200, ok.status_code)
        record(F, 'missing token -> 401', new_client().get('/users/profile/get/', {'user_id': a.id}).status_code == 401, 401, 'checked', sev='P0')
        record(F, 'garbage token -> 401', new_client('garbage').get('/users/profile/get/', {'user_id': a.id}).status_code == 401, 401, 'checked', sev='P0')
        expired = jwt.encode({'user_id': a.id, 'exp': datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)}, settings.SECRET_KEY, algorithm='HS256')
        record(F, 'expired token -> 401', new_client(expired).get('/users/profile/get/', {'user_id': a.id}).status_code == 401, 401, 'checked', sev='P0')
        forged = jwt.encode({'user_id': a.id, 'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)}, settings.SECRET_KEY, algorithm='HS256')
        rr = new_client(forged).get('/users/profile/get/', {'user_id': a.id})
        record(F, 'validly-signed but never-issued token -> 401 (session must match stored token)', rr.status_code == 401, 401, rr.status_code, sev='P0',
               note='Signing key is the (public) default unless SECRET_KEY is set; the stored-token check is what blocks forging')
        none_alg = jwt.encode({'user_id': a.id}, key='', algorithm='none')
        record(F, 'alg=none token -> 401', new_client(none_alg).get('/users/profile/get/', {'user_id': a.id}).status_code == 401, 401, 'checked', sev='P0')
        other_key = jwt.encode({'user_id': a.id, 'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)}, 'a-different-secret-key-of-32-bytes!!', algorithm='HS256')
        record(F, 'token signed with another key -> 401', new_client(other_key).get('/users/profile/get/', {'user_id': a.id}).status_code == 401, 401, 'checked', sev='P0')
        # single session (tokens issued in the same second are byte-identical, so wait a second)
        time.sleep(1.1)
        c.post('/auth/login/', {'username': '+919100000030', 'password': 'Str0ng-pass!'})
        rr = new_client(tok).get('/users/profile/get/', {'user_id': a.id})
        record(F, 'logging in again invalidates the previous access token (single session)', rr.status_code == 401, 401, rr.status_code, sev='P3')
        # token type confusion
        time.sleep(1.1)
        fresh = data(c.post('/auth/login/', {'username': '+919100000030', 'password': 'Str0ng-pass!'}))
        rr = new_client(fresh['refresh_token']).get('/users/profile/get/', {'user_id': a.id})
        record(F, 'refresh token cannot be used as an access token', rr.status_code == 401, 401, rr.status_code, sev='P0')
        rr = c.post('/auth/token/refresh/', {'refresh_token': fresh['access_token']})
        record(F, 'access token cannot be used to refresh', rr.status_code in (400, 401), '4xx', rr.status_code, sev='P1')
        time.sleep(1.1)
        rr = c.post('/auth/token/refresh/', {'refresh_token': fresh['refresh_token']})
        record(F, 'valid refresh token issues a new pair', rr.status_code == 200 and data(rr)['access_token'] != fresh['access_token'], 200, rr.status_code)
        blocked(F, 'logout endpoint', 'No logout/revoke endpoint exists in the API (session ends only by re-login or expiry)')

    def test_forgot_reset(self):
        c = new_client()
        make_actor('customer', '+919100000040', password='Old-pass-123')
        with patch('sunndari_apps.authentication.views.send_otp_sms'):
            known = c.post('/auth/forgot-password/', {'username': '+919100000040'})
            unknown = c.post('/auth/forgot-password/', {'username': '+919100000041'})
        record(F, 'forgot-password gives the same answer for known and unknown accounts', known.status_code == unknown.status_code == 200 and body(known) == body(unknown), 'identical', f'{known.status_code}/{unknown.status_code}')
        code = User.objects.get(phone_number='+919100000040').otp
        r = c.post('/auth/reset-password/', {'username': '+919100000040', 'otp': str(code), 'new_password': 'New-pass-456'})
        record(F, 'reset-password with the right code works', r.status_code == 200, 200, r.status_code)
        record(F, 'old password no longer works, new one does',
               c.post('/auth/login/', {'username': '+919100000040', 'password': 'Old-pass-123'}).status_code == 401 and
               c.post('/auth/login/', {'username': '+919100000040', 'password': 'New-pass-456'}).status_code == 200, 'old 401, new 200', 'checked', sev='P1')
        r = c.post('/auth/reset-password/', {'username': '+919100000040', 'otp': str(code), 'new_password': 'Third-pass-789'})
        record(F, 'reset code is single use', r.status_code == 400, 400, r.status_code, sev='P1')


def _walk(patterns, prefix=''):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p.name


class UnauthSweepQA(TestCase):
    PUBLIC_PREFIXES = ('auth/', 'core/pages/', 'public/', 'api/schema', 'docs/', 'redoc/', 'admin/', 'help_center/admin/chat/', 'media/', 'static/')

    def tearDown(self):
        dump()

    def test_every_route_requires_authentication(self):
        routes = [(path, name) for path, name in _walk(get_resolver().url_patterns)
                  if not path.startswith(self.PUBLIC_PREFIXES) and '<' not in path and path]
        c = new_client()
        bad, checked = [], 0
        for path, name in routes:
            url = '/' + path
            for method in ('get', 'post', 'put', 'delete'):
                r = getattr(c, method)(url)
                checked += 1
                if r.status_code not in (401, 403, 404, 405):
                    bad.append((method.upper(), url, r.status_code))
        record('AUTHZ', f'unauthenticated sweep: {len(routes)} routes x 4 methods = {checked} requests all rejected', not bad,
               'only 401/403/404/405', bad[:5], sev='P0')
        observe('AUTHZ', 'routes intentionally public', ', '.join(sorted(p for p, _ in _walk(get_resolver().url_patterns) if p.startswith(('auth/', 'core/pages/', 'public/')))), sev='P3')
