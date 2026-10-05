import json

from django.test import TransactionTestCase

from qa.harness import record, observe, unverified, body, data, is_2xx, dump, new_client
from qa import world as w

F = 'VALIDATION'

HOSTILE = [
    ('missing', '__MISSING__'), ('null', None), ('empty string', ''), ('whitespace', '   '), ('very long (5000)', 'x' * 5000),
    ('empty list', []), ('empty object', {}), ('text for number', 'abc'), ('huge number', 10 ** 30), ('negative', -1), ('zero', 0),
    ('float string', '1e30'), ('SQL injection', "' OR '1'='1'; DROP TABLE users;--"), ('HTML/script', '<script>alert(1)</script><img src=x onerror=alert(1)>'),
    ('path traversal', '../../../etc/passwd'), ('emoji/unicode', '😀 ‮ ünï'), ('NUL byte', 'a\x00b'), ('boolean', True), ('nested list', [[1, 2], [3]]),
]


def _fuzz(client, method, url, valid, flow_name, multipart=False, skip_fields=()):
    """Mutates every field of a known-good payload and reports crashes / leaked internals."""
    crashes, leaks, nonjson, nonobject, total = [], [], [], [], 0
    call = getattr(client, method)

    def send(payload):
        nonlocal total
        total += 1
        try:
            resp = call(url, payload, format='multipart' if multipart else 'json')
        except Exception as exc:                       # the test client itself blew up serialising it
            return None
        text = resp.content.decode('utf-8', 'replace')[:4000]
        if resp.status_code >= 500:
            crashes.append((url, payload_summary(payload), resp.status_code, text[:120]))
        if any(marker in text for marker in ('Traceback (most recent call last)', '/Users/rayyanshaikh', 'sqlite3.', 'django.db.utils', 'File "/')):
            leaks.append((url, payload_summary(payload)))
        if resp.status_code != 204 and 'application/json' not in resp.get('Content-Type', '') and resp.status_code < 500 and not resp.streaming:
            nonjson.append((url, resp.status_code, resp.get('Content-Type')))
        return resp

    for field in valid:
        if field in skip_fields:
            continue
        for _label, value in HOSTILE:
            payload = dict(valid)
            if value == '__MISSING__':
                payload.pop(field)
            else:
                payload[field] = value
            send(payload)
    send({**valid, 'is_admin': True, 'role': 'admin', '__class__': 'x', 'user_id': 1, 'approval_status_id': 1})
    for raw in (None, [], 'just a string', 123):
        total += 1
        try:
            resp = call(url, raw, format='json')
        except Exception:
            continue
        if resp.status_code >= 500:
            nonobject.append(repr(raw))
    record(flow_name, f'{method.upper()} {url}: non-object JSON body ([], "text", 123, null) -> controlled 400, not 500', not nonobject, '400', f'HTTP 500 for {nonobject}', sev='P2',
           note='SerializerValidations._copy_request_data returns list.copy() and then calls .update() on it')
    record(flow_name, f'{method.upper()} {url}: {total} hostile requests, no 5xx crash', not crashes, 'no 500', crashes[:4], sev='P2')
    record(flow_name, f'{method.upper()} {url}: no traceback / path / SQL leakage to the client', not leaks, 'clean', leaks[:3], sev='P1')
    record(flow_name, f'{method.upper()} {url}: error responses are JSON, never HTML', not nonjson, 'JSON', nonjson[:3], sev='P3')
    return total


def payload_summary(payload):
    if isinstance(payload, dict):
        return {k: (str(v)[:30] if not isinstance(v, (int, float, bool, type(None))) else v) for k, v in payload.items()}
    return str(payload)[:30]


class FuzzQA(TransactionTestCase):
    # Real autocommit semantics (like production): one failed request must not poison the next.
    def setUp(self):
        w.seed_statuses()
        self.art = w.make_bookable_artist('+919900000001', 'Fuzz Artist')
        self.cus = w.make_customer('+919900000002', 'Fuzz Customer')
        self.admin = w.make_admin('+919900000003')

    def tearDown(self):
        dump()

    def test_json_endpoints(self):
        A, C = self.art, self.cus
        pkg = A.package.package_id
        total = 0
        bid = w.confirmed_booking(C, A, day=3)
        total += _fuzz(A.client, 'put', '/artists/profile/update/', {'display_name': 'Fz', 'date_of_birth': '1990-01-01', 'instagram_url': 'https://instagram.com/fz', 'profile_type': 'studio',
                                                                      'bio': 'b', 'years_experience': 3, 'city': 'Lucknow', 'service_radius_km': 10, 'travel_time_before_minutes': 10, 'return_buffer_minutes': 10}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/packages/create/', {'sub_category_id': A.sub.sub_category_id, 'name': 'P', 'price': '1000', 'duration_minutes': 60, 'description': 'd',
                                                                        'makeup_type': 'HD', 'brands': ['MAC'], 'product_details': 'x', 'inclusions': ['a']}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/addons/create/', {'name': 'Ad', 'price': '100', 'duration_minutes': 10, 'description': 'd', 'package_ids': [pkg]}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/service_areas/add/', {'city': 'Kanpur', 'travel_charge_type': 'per_visit', 'charge_amount': '50'}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/payout_account/set/', {'account_holder_name': 'H', 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234', 'upi_id': 'a@b'}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/availability/block/add/', {'block_date': '2032-01-05', 'note': 'n'}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/availability/schedule/set/', {'day_of_week': 3, 'start_time': '09:00:00', 'end_time': '17:00:00'}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/portfolio/reorder/', {'portfolio_ids': [1, 2]}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/profile/specialities/set/', {'sub_category_ids': [A.sub.sub_category_id]}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled', 'reason': 'r'}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': 123456}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/bookings/reschedule/request/', {'booking_id': bid, 'proposed_date': w.fmt_date(w.future_date(8)), 'proposed_start_time': '12:00:00', 'reason': 'r'}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/clients/note/set/', {'customer_id': C.id, 'note': 'n'}, 'VALIDATION')
        total += _fuzz(A.client, 'post', '/artists/brands/request/', {'name': 'Brand X'}, 'VALIDATION')
        total += _fuzz(A.client, 'put', '/artists/profile/accepting_bookings/', {'is_accepting_bookings': True}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/customers/bookings/create/', {'artist_id': A.profile.artist_id, 'package_id': pkg, 'location_type_id': w.location('Studio').location_type_id,
                                                                         'booking_date': w.fmt_date(w.future_date(20)), 'start_time': '10:00:00', 'address_id': C.address.address_id, 'notes': 'n', 'addon_ids': []}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/users/address/create/', {'address_line_1': 'x', 'address_line_2': 'y', 'city': 'Lucknow', 'pin_code': '226001', 'is_default': False}, 'VALIDATION')
        total += _fuzz(C.client, 'put', '/users/profile/update/', {'name': 'N', 'fcm_token': 'tok'}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/chat/messages/create/', {'booking_id': bid, 'content': 'hi'}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/help_center/messages/create/', {'content': 'hi'}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/customers/reviews/create/', {'booking_id': bid, 'rating': 5, 'comment': 'c'}, 'VALIDATION')
        total += _fuzz(C.client, 'put', '/customers/bookings/cancel/', {'booking_id': bid, 'reason': 'r'}, 'VALIDATION')
        total += _fuzz(C.client, 'put', '/customers/bookings/reschedule/respond/', {'reschedule_id': 1, 'decision': 'accepted'}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/customers/payments/initiate/', {'booking_id': bid, 'amount': '100.00', 'payment_type': 'advance'}, 'VALIDATION')
        total += _fuzz(C.client, 'post', '/customers/payments/verify/', {'razorpay_order_id': 'o', 'razorpay_payment_id': 'p', 'razorpay_signature': 's'}, 'VALIDATION')
        total += _fuzz(self.admin.client, 'post', '/admin-panel/brands/create/', {'name': 'Admin Brand'}, 'VALIDATION')
        total += _fuzz(self.admin.client, 'put', '/admin-panel/artists/approve/', {'artist_id': A.profile.artist_id, 'message': 'm'}, 'VALIDATION')
        total += _fuzz(self.admin.client, 'put', '/admin-panel/artists/documents/verify/', {'document_id': 1, 'decision': 'approved', 'reason': 'r'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/register/', {'name': 'N', 'phone_number': '+919911100001', 'password': 'Str0ng-pass!', 'role': 'customer'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/login/', {'username': '+919900000002', 'password': 'whatever'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/phone-otp/request/', {'phone_number': '+919911100002', 'role': 'customer'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/phone-otp/verify/', {'phone_number': '+919900000002', 'otp': '123456'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/forgot-password/', {'username': '+919900000002'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/reset-password/', {'username': '+919900000002', 'otp': '123456', 'new_password': 'Newpass-123'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/token/refresh/', {'refresh_token': 'abc'}, 'VALIDATION')
        total += _fuzz(new_client(), 'post', '/auth/google/', {'id_token': 'abc', 'role': 'customer'}, 'VALIDATION')
        observe(F, 'total hostile requests sent in the JSON fuzz matrix', total, sev='P3')

    def test_multipart_endpoints(self):
        A, C = self.art, self.cus
        total = 0
        total += _fuzz(A.client, 'post', '/artists/documents/create/', {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567', 'file': w.png()}, 'VALIDATION', multipart=True, skip_fields=('file',))
        total += _fuzz(A.client, 'post', '/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': A.sub.sub_category_id, 'caption': 'c', 'file': w.png()}, 'VALIDATION', multipart=True, skip_fields=('file',))
        total += _fuzz(C.client, 'post', '/help_center/tickets/create/', {'issue_type': 'payment', 'subject': 's', 'description': 'd'}, 'VALIDATION', multipart=True)
        observe(F, 'multipart fuzz requests', total, sev='P3')

    def test_query_parameter_fuzz(self):
        A, C = self.art, self.cus
        crashes, leaks, total = [], [], 0
        urls = {A.client: ['/artists/packages/get_all/', '/artists/portfolio/get_all/', '/artists/documents/get_all/', '/artists/addons/get_all/', '/artists/reviews/get_all/', '/artists/clients/get_all/',
                           '/artists/bookings/get_all/', '/artists/bookings/reschedule/get_all/', '/artists/customer_reviews/get_all/', '/artists/brands/requests/get_all/', '/artists/review/feedback/get_all/'],
                C.client: ['/customers/bookings/get_all/', '/customers/artists/search/', '/customers/reviews/get_all/', '/users/address/get_all/', '/notifications/get_all/', '/core/service-category/get_all/',
                           '/core/brands/get_all/', '/customers/bookings/reschedule/get_all/', '/help_center/tickets/get_all/']}
        params = [{'page_num': v} for v in ('0', '-1', 'abc', '99999', '1e3', '')] + [{'limit': v} for v in ('0', '-5', 'abc', '100000', '')] + \
                 [{'sort_by': v} for v in ("x; DROP TABLE users", "__class__", "password", "access_token", "bookingId'--", '🙂')] + [{'sort_order': v} for v in ('sideways', "asc; --")] + \
                 [{'filter_key': k, 'filter_value': v} for k in ("password", "access_token", "user__password", "bookingId'--", "id") for v in ("1", "' OR 1=1 --", "x" * 300)] + \
                 [{'search_key': v} for v in ("' OR '1'='1", '%', '_', '<script>', 'x' * 1000)] + [{'values': v} for v in ('nonsense', 'a,b,c', "x'--", ',,,')] + \
                 [{'from_date': v} for v in ('31-02-99', 'garbage', '99-99-99')] + [{'artist_id': v} for v in ('abc', '-1', '99999999999999999999')]
        for client, paths in urls.items():
            for path in paths:
                for p in params:
                    total += 1
                    resp = client.get(path, p)
                    text = resp.content.decode('utf-8', 'replace')[:3000]
                    if resp.status_code >= 500:
                        crashes.append((path, p, resp.status_code))
                    if any(m in text for m in ('Traceback', '/Users/rayyanshaikh', 'sqlite3.', 'django.db.utils')):
                        leaks.append((path, p))
                    if p.get('filter_key') in ('password', 'access_token', 'user__password') and ('pbkdf2' in text or 'eyJ' in text):
                        leaks.append((path, p, 'secret in response'))
        record(F, f'query-parameter fuzz ({total} requests across {sum(len(v) for v in urls.values())} list endpoints): no 5xx', not crashes, 'no 500', crashes[:6], sev='P2')
        record(F, 'query-parameter fuzz: no internals / secrets leaked (incl. filter_key=password/access_token)', not leaks, 'clean', leaks[:4], sev='P0')

    def test_content_type_and_malformed_bodies(self):
        A = self.art
        bad = []
        for url, method in (('/artists/profile/update/', 'put'), ('/artists/packages/create/', 'post'), ('/customers/bookings/create/', 'post'), ('/auth/login/', 'post')):
            client = A.client if 'auth' not in url else new_client()
            for ctype, raw in (('application/json', '{bad json'), ('application/json', ''), ('application/json', '[]'), ('application/json', 'null'), ('text/plain', 'hello'),
                               ('application/xml', '<a/>'), ('application/json', '{"a":' + '[' * 500 + ']' * 500 + '}'), ('multipart/form-data; boundary=x', 'garbage')):
                resp = getattr(client, method)(url, data=raw, content_type=ctype)
                if resp.status_code >= 500:
                    bad.append((method, url, ctype, raw[:20], resp.status_code))
        record(F, 'malformed bodies / wrong content types never crash the server', not bad, 'no 5xx', bad[:5], sev='P2')
        huge = new_client().post('/auth/login/', data=json.dumps({'username': 'x' * 2_000_000, 'password': 'y'}), content_type='application/json')
        record(F, 'a 2 MB JSON body is handled (rejected or processed) without a crash', huge.status_code < 500, '<500', huge.status_code, sev='P2')
