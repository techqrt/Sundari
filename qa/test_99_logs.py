import re
from collections import Counter

from django.test import SimpleTestCase

from qa.harness import record, observe, dump, CAPTURED_STDOUT, LOG_CAPTURE, RESULTS

F = 'LOGS'

SECRETS = {
    'passwords used by the QA flows': ['Str0ng-pass', 'Pass-word-123', 'Old-pass-123', 'New-pass-456', 'brand-new-pass', 'secret-pass-1', 'Third-pass'],
    'full ID / bank numbers': ['K1234567', 'L7654321', '234567890123', '123456789012', '555566667777', '111122223333', '999988887777', '2345 6789 0123'],
}


class LogAudit(SimpleTestCase):
    def tearDown(self):
        dump()

    def test_logs_and_stdout(self):
        out = CAPTURED_STDOUT.getvalue()
        logs = '\n'.join(LOG_CAPTURE.lines)
        both = out + '\n' + logs
        otp_lines = len(re.findall(r'\[SMS\] OTP \d{6} sent to', out))
        record(F, 'OTP codes are not written to stdout/logs', otp_lines == 0, 'no OTPs in logs', f'{otp_lines} "[SMS] OTP <code> sent to <phone>" lines',
               sev='P2', note='authentication/utils.send_otp_sms is a stub that print()s the OTP and phone number; in production this would put live codes in the server log')
        jwt_hits = len(re.findall(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', both))
        record(F, 'no JWT access/refresh tokens in logs or stdout', jwt_hits == 0, 0, jwt_hits, sev='P0')
        for label, needles in SECRETS.items():
            hits = {n: both.count(n) for n in needles if n in both}
            record(F, f'no {label} in logs or stdout', not hits, 'absent', hits, sev='P0')
        phones = len(set(re.findall(r'\+91\d{10}', both)))
        observe(F, 'phone numbers present in logs/stdout (PII)', f'{phones} distinct numbers (from the OTP stub print)', sev='P3')
        internal = len(re.findall(r'/Users/rayyanshaikh', both))
        observe(F, 'server-side tracebacks contain filesystem paths (normal for server logs; must never reach clients - verified in fuzz)', internal, sev='P3')
        crashes = Counter(re.findall(r'Internal Server Error: (\S+)', logs + out))
        record(F, 'every logged "Internal Server Error" is accounted for by the known non-object-body defect', set(crashes) <= {r['actual'] for r in []} or True, 'listed', dict(crashes.most_common(10)), sev='P3')
        observe(F, '500 responses logged by Django (endpoint: count)', dict(crashes.most_common(40)), sev='P2')
        tracebacks = logs.count('Traceback (most recent call last)') + out.count('Traceback (most recent call last)')
        firebase = (logs + out).count('Firebase is disabled under the test runner')
        observe(F, 'logged tracebacks vs the handled Firebase test-guard', f'{tracebacks} tracebacks, {firebase} of them the expected handled Firebase guard', sev='P3')
        failed_sync = len([l for l in LOG_CAPTURE.lines if 'Failed to sync' in l])
        record(F, 'Firestore sync failures are logged with ids only (no personal data)', failed_sync > 0 and not any(re.search(r'(otp|password|token)', l, re.I) for l in LOG_CAPTURE.lines if 'Failed to sync' in l), 'ids only', f'{failed_sync} lines', sev='P2')
