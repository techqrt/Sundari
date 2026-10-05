from django.db import connection
from django.test import TestCase

from sunndari_apps.artists.models import ArtistProfile, ArtistDocument, ArtistPayoutAccount
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ApprovalStatus, ServiceCategory, ServiceSubCategory, LocationType
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client, LOG_CAPTURE, CAPTURED_STDOUT
from qa import world as w

F = 'KYC'


def register_artist_over_http(phone, name):
    c = new_client()
    r = c.post('/auth/register/', {'name': name, 'phone_number': phone, 'password': 'Str0ng-pass!', 'role': 'artist'}, format='json')
    token = data(r)['access_token']
    return new_client(token), User.objects.get(phone_number=phone)


class KycQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.admin = w.make_admin('+919500000001')
        cls.cust = w.make_customer('+919500000002', 'KYC Customer')
        cls.art = w.make_bookable_artist('+919500000003', 'KYC Artist', approved=False)

    def tearDown(self):
        dump()

    def _doc(self, client, **kw):
        files = {'file': w.png('front.png')}
        if kw.pop('back', False):
            files['back_file'] = w.png('back.png')
        body_ = {'document_type': 'id_proof', **kw, **files}
        return client.post('/artists/documents/create/', body_, format='multipart')

    def test_kyc_types_and_validation(self):
        c = self.art.client
        cases = [('aadhaar', '2345 6789 0123', True), ('voter_id', 'ABC1234567', True), ('passport', 'K1234567', False), ('driving_licence', 'MH12-2011-0012345', True)]
        for id_type, number, back in cases:
            r = self._doc(c, id_type=id_type, document_number=number, back=back)
            record(F, f'{id_type}: valid submission accepted', r.status_code == 201, 201, r.status_code, sev='P1')
            row = ArtistDocument.objects.filter(artist=self.art.profile, document_type='id_proof').first()
            record(F, f'{id_type}: database stores the distinct id_type', row is not None and row.id_type == id_type, id_type, getattr(row, 'id_type', None), sev='P1')
        for label, kw, expect in [
            ('invalid id_type', dict(id_type='national_id', document_number='K1234567'), 400),
            ('missing id_type', dict(document_number='K1234567'), 400),
            ('missing document number', dict(id_type='passport'), 400),
            ('empty document number', dict(id_type='passport', document_number=''), 400),
            ('aadhaar wrong length', dict(id_type='aadhaar', document_number='1234', back=True), 400),
            ('aadhaar starting with 0/1', dict(id_type='aadhaar', document_number='123456789012', back=True), 400),
            ('voter id wrong pattern', dict(id_type='voter_id', document_number='123', back=True), 400),
            ('passport wrong pattern', dict(id_type='passport', document_number='ZZ'), 400),
            ('driving licence wrong pattern', dict(id_type='driving_licence', document_number='x', back=True), 400),
            ('aadhaar without back image', dict(id_type='aadhaar', document_number='234567890123'), 400),
            ('SQL-ish document number', dict(id_type='passport', document_number="K1'; DROP TABLE users;--"), 400),
        ]:
            r = self._doc(c, **kw)
            record(F, f'rejects {label}', r.status_code == expect, expect, r.status_code, sev='P1')
        r = c.post('/artists/documents/create/', {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567'}, format='multipart')
        record(F, 'rejects a submission with no image at all', r.status_code == 400, 400, r.status_code, sev='P1')
        r = c.post('/artists/documents/create/', {'document_type': 'selfie', 'file': w.png()}, format='multipart')
        record(F, 'rejects an unknown document_type', r.status_code == 400, 400, r.status_code, sev='P1')
        r = self._doc(c, id_type='passport', document_number='K1234567')
        r = self._doc(c, id_type='passport', document_number='L7654321')
        n = ArtistDocument.objects.filter(artist=self.art.profile, document_type='id_proof').count()
        record(F, 'resubmitting an ID proof replaces the previous one (exactly one remains)', n == 1, 1, n, sev='P2')
        row = ArtistDocument.objects.filter(artist=self.art.profile, document_type='id_proof').first()
        record(F, 'resubmission resets verification to pending', row.verification_status.name == 'pending', 'pending', row.verification_status.name, sev='P1')
        # exposure
        listing = body(c.get('/artists/documents/get_all/'))
        flat = str(listing)
        record('KYC-SECURITY', 'owner API shows a masked document number only', 'L7654321' not in flat and 'XXXX' in flat, 'masked', flat[:160], sev='P0')
        with connection.cursor() as cur:
            cur.execute('select document_number, document_number_encrypted from artist_documents where artist_id=%s and document_type=%s', [self.art.profile.artist_id, 'id_proof'])
            display, enc = cur.fetchone()
        record('KYC-SECURITY', 'raw ID number is not stored in plaintext in the database', 'L7654321' not in str(display) and 'L7654321' not in str(enc), 'encrypted/masked at rest', f'{display} / {str(enc)[:20]}', sev='P0')
        self._doc(c, id_type='aadhaar', document_number='234567890123', back=True)
        with connection.cursor() as cur:
            cur.execute("select document_number, document_number_encrypted from artist_documents where artist_id=%s and id_type='aadhaar'", [self.art.profile.artist_id])
            display, enc = cur.fetchone()
        record('KYC-SECURITY', 'Aadhaar number is never stored in full (last 4 only, nothing encrypted)', '234567890123' not in str(display) and enc is None, 'last 4 only', f'{display}/{enc}', sev='P0')
        # who can reach it
        for label, client in (('customer', self.cust.client), ('anonymous', new_client())):
            r = client.get('/artists/documents/get_all/')
            record('KYC-SECURITY', f'{label} cannot list artist KYC documents', not is_2xx(r), 'rejected', r.status_code, sev='P0')
        approved_art = w.make_bookable_artist('+919500000004', 'Public Artist')
        public = str(body(self.cust.client.get('/customers/artists/get/', {'artist_id': approved_art.profile.artist_id}))) + str(body(self.cust.client.get('/artists/profile/get/', {'artist_id': approved_art.profile.artist_id})))
        record('KYC-SECURITY', 'no KYC/bank field names appear in public artist responses', not any(k in public.lower() for k in ('document_number', 'documentnumber', 'idnumber', 'ifsc', 'bankaccount', 'fileurl')), 'absent', 'checked', sev='P0')
        bad = body(c.get('/artists/documents/get/', {'document_id': 999999}))
        record('KYC-SECURITY', 'error responses do not leak internals (paths, SQL, tracebacks)', not any(k in str(bad) for k in ('Traceback', '/Users/', 'SELECT', 'sqlite')), 'clean', str(bad)[:150], sev='P1')
        # admin review of docs
        a = self.admin.client
        docs = data(a.get('/admin-panel/artists/documents/get_all/', {'artist_id': self.art.profile.artist_id})) or []
        record(F, 'admin can list artist documents incl. full ID number for non-Aadhaar types', any(d['idType'] == 'passport' and d['idNumber'] == 'L7654321' for d in docs) or any(d['idType'] == 'aadhaar' for d in docs), 'visible to admin', [d['idType'] for d in docs], sev='P2')
        passport = next((d for d in docs if d['documentType'] == 'id_proof'), None)
        r = a.put('/admin-panel/artists/documents/verify/', {'document_id': passport['documentId'], 'decision': 'rejected'}, format='json')
        record(F, 'admin rejection requires a reason', r.status_code == 400, 400, r.status_code, sev='P3')
        r = a.put('/admin-panel/artists/documents/verify/', {'document_id': passport['documentId'], 'decision': 'rejected', 'reason': 'blurry'}, format='json')
        record(F, 'admin can reject a document with a reason', r.status_code == 200, 200, r.status_code, sev='P1')
        r = a.put('/admin-panel/artists/documents/verify/', {'document_id': passport['documentId'], 'decision': 'approved'}, format='json')
        record(F, 'a decided document cannot be flipped silently', r.status_code == 400, 400, r.status_code, sev='P2')

    def test_bank_details(self):
        c = self.art.client
        ok = {'account_holder_name': 'KYC Artist', 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234'}
        r = c.put('/artists/payout_account/set/', ok, format='json')
        record('BANK', 'add bank account', r.status_code == 200, 200, r.status_code, sev='P1')
        g = data(c.get('/artists/payout_account/get/')) or {}
        record('BANK', 'GET returns masked number + holder + IFSC, never the raw number', g.get('bankAccountNumberMasked') == 'XXXXXXXX9012' and '123456789012' not in str(g), 'masked', g, sev='P0')
        r = c.put('/artists/payout_account/set/', {**ok, 'bank_account_number': '555566667777', 'upi_id': 'artist@upi'}, format='json')
        g = data(c.get('/artists/payout_account/get/')) or {}
        record('BANK', 'update replaces the account (single row) and keeps UPI', g.get('bankAccountNumberMasked') == 'XXXXXXXX7777' and ArtistPayoutAccount.objects.filter(artist=self.art.profile).count() == 1, 'one updated account', g, sev='P1')
        for label, kw in {'IFSC lowercase-invalid': {'ifsc_code': 'hdfc123'}, 'IFSC 11 chars bad pattern': {'ifsc_code': 'HDFC1001234'}, 'short account number': {'bank_account_number': '123'},
                          'account number with letters': {'bank_account_number': 'ABCDEFGHIJ12'}, 'over-long account number': {'bank_account_number': '1' * 31},
                          'empty holder name': {'account_holder_name': ''}}.items():
            r = c.put('/artists/payout_account/set/', {**ok, **kw}, format='json')
            record('BANK', f'rejects {label}', r.status_code == 400, 400, r.status_code, sev='P2')
        other = w.make_bookable_artist('+919500000005', 'Dup Bank Artist')
        r = other.client.put('/artists/payout_account/set/', {**ok, 'bank_account_number': '555566667777'}, format='json')
        observe('BANK', 'two artists can register the same bank account number', f'HTTP {r.status_code}: encrypted non-deterministically so duplicates cannot be detected', sev='P3', note='Fraud-risk design note; no uniqueness possible without a deterministic hash')
        record('BANK', 'customer cannot set a payout account', not is_2xx(self.cust.client.put('/artists/payout_account/set/', ok, format='json')), 'rejected', 'checked', sev='P0')
        record('BANK', 'unauthenticated cannot read/set payout account', not is_2xx(new_client().get('/artists/payout_account/get/')) and not is_2xx(new_client().put('/artists/payout_account/set/', ok, format='json')), 'rejected', 'checked', sev='P0')
        with connection.cursor() as cur:
            cur.execute('select bank_account_number from artist_payout_accounts where artist_id=%s', [self.art.profile.artist_id])
            raw = cur.fetchone()[0]
        record('BANK', 'bank account number encrypted at rest', '555566667777' not in raw and raw.startswith('gAAAA'), 'ciphertext', raw[:12], sev='P1')
        acct = ArtistPayoutAccount.objects.get(artist=self.art.profile)
        record('BANK', 'changing the account resets its verification to pending', acct.verification_status.name == 'pending', 'pending', acct.verification_status.name, sev='P2')
        observe('BANK', 'payout provider integration', 'NOT IMPLEMENTED: bank details are stored only; no endpoint verifies an account and no payout provider/ledger exists (owner skipped earnings & payouts)', sev='P1')
        observe('BANK', 'verification of payout accounts', 'No admin endpoint can mark a payout account verified (verification_status stays pending forever)', sev='P2')


class ApprovalWorkflowQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.admin = w.make_admin('+919600000001')
        cls.cust = w.make_customer('+919600000002', 'Approval Customer')

    def tearDown(self):
        dump()

    def _onboard(self, phone, name):
        c, user = register_artist_over_http(phone, name)
        cat, _ = ServiceCategory.objects.get_or_create(name='QA Makeup')
        sub, _ = ServiceSubCategory.objects.get_or_create(category=cat, name='QA Bridal')
        loc, _ = LocationType.objects.get_or_create(name='Studio')
        addr = w.CustomerAddress.objects.get(address_id=w.CustomerAddress().create(user_id=user.user_id, address_line_1='1 Rd', city='Lucknow', pin_code='226001'))
        steps = {}
        steps['profile'] = c.put('/artists/profile/update/', {'display_name': name, 'date_of_birth': '1990-01-01', 'profile_type': 'freelance', 'bio': 'bio', 'city': 'Lucknow', 'base_address_id': addr.address_id}, format='json').status_code
        steps['sample'] = c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': sub.sub_category_id, 'is_work_sample': 'true', 'file': w.png()}, format='multipart').status_code
        steps['service'] = c.post('/artists/services/add/', {'sub_category_id': sub.sub_category_id}, format='json').status_code
        steps['package'] = c.post('/artists/packages/create/', {'sub_category_id': sub.sub_category_id, 'name': 'P', 'price': '1500', 'duration_minutes': 60}, format='json').status_code
        steps['location'] = c.post('/artists/locations/add/', {'location_type_id': loc.location_type_id}, format='json').status_code
        steps['schedule'] = c.post('/artists/availability/schedule/set/', {'day_of_week': 2, 'start_time': '09:00:00', 'end_time': '18:00:00'}, format='json').status_code
        steps['document'] = c.post('/artists/documents/create/', {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567', 'file': w.png()}, format='multipart').status_code
        steps['bank'] = c.put('/artists/payout_account/set/', {'account_holder_name': name, 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234'}, format='json').status_code
        return c, user, steps

    def test_state_machine(self):
        F2 = 'APPROVAL'
        c, user, steps = self._onboard('+919600000010', 'Flow Artist')
        record(F2, 'onboarding setup calls all succeed over HTTP', all(v in (200, 201) for v in steps.values()), 'all 2xx', steps, sev='P1')
        profile = ArtistProfile.objects.get(user=user)
        aid = profile.artist_id
        a = self.admin.client
        st = lambda: data(c.get('/artists/onboarding/status/'))
        record(F2, 'initial status is in_progress, agreement step incomplete', st()['status'] == 'in_progress' and not st()['steps']['agreement'], 'in_progress', st()['status'], sev='P2')
        r = c.post('/artists/onboarding/submit/', {}, format='json')
        record(F2, 'submit refused while a step (agreement) is incomplete', r.status_code == 400, 400, r.status_code, sev='P1')
        record(F2, 'admin cannot approve or reject an artist who never submitted', not is_2xx(a.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json')) and not is_2xx(a.put('/admin-panel/artists/reject/', {'artist_id': aid, 'reason': 'x'}, format='json')), 'both refused', 'checked', sev='P1')
        c.put('/artists/profile/agreement/accept/', {}, format='json')
        r = c.post('/artists/onboarding/submit/', {}, format='json')
        record(F2, 'complete onboarding submits', r.status_code == 200 and st()['status'] == 'submitted', 'submitted', st()['status'], sev='P1')
        r = c.post('/artists/onboarding/submit/', {}, format='json')
        observe(F2, 'second submit while already submitted', f'HTTP {r.status_code} (idempotent re-submit re-stamps submittedForReviewAt)', sev='P3')
        queue = [x['artistId'] for x in data(a.get('/admin-panel/artists/review_queue/get_all/'))['data']]
        record(F2, 'submitted artist appears in the admin review queue', aid in queue, 'listed', queue, sev='P1')
        detail = data(a.get('/admin-panel/artists/review/get/', {'artist_id': aid})) or {}
        record(F2, 'admin review detail shows registration fields + work sample', detail.get('displayName') == 'Flow Artist' and len(detail.get('workSamples', [])) == 1, 'visible', sorted(detail)[:6], sev='P2')
        r = a.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json')
        record(F2, 'approval blocked while the ID proof is unverified', r.status_code == 400 and ArtistProfile.objects.get(artist_id=aid).approval_status.name == 'pending', 'refused', r.status_code, sev='P1')
        for who, cl in (('customer', self.cust.client), ('artist', c), ('anonymous', new_client())):
            r = cl.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json')
            record(F2, f'{who} cannot approve', not is_2xx(r) and ArtistProfile.objects.get(artist_id=aid).approval_status.name == 'pending', 'refused', r.status_code, sev='P0')
        doc = ArtistDocument.objects.get(artist_id=aid)
        a.put('/admin-panel/artists/documents/verify/', {'document_id': doc.document_id, 'decision': 'approved'}, format='json')
        r = a.put('/admin-panel/artists/reject/', {'artist_id': aid, 'reason': 'Please add a clearer work sample'}, format='json')
        s = st()
        record(F2, 'rejection stores reason, status=rejected, leaves the review queue', r.status_code == 200 and s['status'] == 'rejected' and aid not in [x['artistId'] for x in data(a.get('/admin-panel/artists/review_queue/get_all/'))['data']], 'rejected', s['status'], sev='P1')
        fb = data(c.get('/artists/review/feedback/get_all/'))['data']
        record(F2, 'artist can read the admin feedback', fb and fb[0]['message'] == 'Please add a clearer work sample' and fb[0]['decision'] == 'rejected', 'feedback visible', fb, sev='P1')
        record(F2, 'admin cannot approve a rejected artist who has not resubmitted', not is_2xx(a.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json')), 'refused', 'checked', sev='P1')
        r = c.post('/artists/onboarding/submit/', {}, format='json')
        record(F2, 'artist resubmits after rejection and re-enters the queue', r.status_code == 200 and aid in [x['artistId'] for x in data(a.get('/admin-panel/artists/review_queue/get_all/'))['data']] and st()['status'] == 'submitted', 'resubmitted', st()['status'], sev='P1')
        r = a.put('/admin-panel/artists/approve/', {'artist_id': aid, 'message': 'Welcome'}, format='json')
        record(F2, 'admin approves the resubmission', r.status_code == 200 and st()['status'] == 'approved', 'approved', st()['status'], sev='P1')
        record(F2, 'double approval is idempotent', a.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json').status_code == 200, 200, 'checked', sev='P3')
        record(F2, 'approved artist cannot re-submit', c.post('/artists/onboarding/submit/', {}, format='json').status_code == 400, 400, 'checked', sev='P2')
        search = [x['artistId'] for x in data(self.cust.client.get('/customers/artists/search/'))['data']]
        record(F2, 'approved artist is now discoverable by customers', aid in search, 'listed', search, sev='P1')
        hist = [f['decision'] for f in data(c.get('/artists/review/feedback/get_all/'))['data']]
        record(F2, 'feedback history keeps every round (rejected then approved)', hist == ['rejected', 'approved'], ['rejected', 'approved'], hist, sev='P2')
        observe(F2, 'lifecycle vs requirement', 'Implemented: pending -> submitted -> approved/rejected -> resubmit (status label stays "rejected"; owner decided not to add a separate "changes_required" status). A "Draft" state is derived (not_started/in_progress), not stored.', sev='P3')
        # suspended can't be silently reactivated
        ArtistProfile.objects.filter(artist_id=aid).update(approval_status=ApprovalStatus.objects.get(name='suspended'))
        record(F2, 'approve/reject cannot lift a suspension', not is_2xx(a.put('/admin-panel/artists/approve/', {'artist_id': aid}, format='json')) and not is_2xx(a.put('/admin-panel/artists/reject/', {'artist_id': aid, 'reason': 'x'}, format='json')), 'refused', 'checked', sev='P1')
        observe(F2, 'suspension has no API', 'There is no endpoint to suspend or un-suspend an artist (Django admin only)', sev='P3')
