import io
import os
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from PIL import Image

from sunndari_apps.artists.models import Portfolio, PricingPackage, PackageAddOn, ArtistDocument
from sunndari_apps.customers.models import Booking
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump
from qa import world as w

F = 'CONTENT'


def _upload(client, url, name, content, ctype, extra=None, field='file', method='post'):
    payload = {field: SimpleUploadedFile(name, content, content_type=ctype), **(extra or {})}
    return getattr(client, method)(url, payload, format='multipart')


class PortfolioPackageQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.art = w.make_bookable_artist('+919400000001', 'Content Artist')
        cls.cus = w.make_customer('+919400000002', 'Content Customer')

    def tearDown(self):
        dump()

    def test_portfolio_lifecycle(self):
        c, a = self.art.client, self.art
        mk = lambda **kw: c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': a.sub.sub_category_id, 'file': w.png(), **kw}, format='multipart')
        r = mk(caption='first')
        pid = (data(r) or {}).get('portfolio_id')
        record(F, 'portfolio create', r.status_code == 201 and pid, 201, r.status_code, sev='P1')
        ids = [pid] + [data(mk(caption=f'n{i}'))['portfolio_id'] for i in range(2)]
        record(F, 'portfolio listing returns items in creation order', [i['portfolioId'] for i in data(c.get('/artists/portfolio/get_all/'))['data']] == ids, ids, 'checked')
        r = c.put('/artists/portfolio/reorder/', {'portfolio_ids': list(reversed(ids))}, format='json')
        record(F, 'portfolio reorder persists', r.status_code == 200 and [i['portfolioId'] for i in data(c.get('/artists/portfolio/get_all/'))['data']] == list(reversed(ids)), 'reversed', 'checked', sev='P2')
        r = c.put('/artists/portfolio/update/', {'portfolio_id': pid, 'caption': 'edited'}, format='json')
        record(F, 'portfolio edit persists', r.status_code == 200 and Portfolio.objects.get(portfolio_id=pid).caption == 'edited', 'edited', r.status_code, sev='P1')
        stored = Portfolio.objects.get(portfolio_id=pid).file.name
        record(F, 'portfolio file physically stored under MEDIA_ROOT', os.path.exists(os.path.join(settings.MEDIA_ROOT, stored)), 'file exists', stored, sev='P1')
        r = c.delete(f'/artists/portfolio/delete/?portfolio_id={pid}')
        record(F, 'portfolio delete removes the row', r.status_code == 200 and not Portfolio.objects.filter(portfolio_id=pid).exists(), 'deleted', r.status_code, sev='P1')
        record(F, 'portfolio delete also removes the stored file (no orphan)', not os.path.exists(os.path.join(settings.MEDIA_ROOT, stored)), 'file removed', 'file still on disk', sev='P3',
               note='Portfolio.remove() deletes the row only; the uploaded media stays on disk forever')
        for label, kw in {'missing media_type': {'media_type': ''}, 'bad media_type': {'media_type': 'gif'}, 'missing sub_category': {'sub_category_id': ''}}.items():
            r = c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': a.sub.sub_category_id, 'file': w.png(), **kw}, format='multipart')
            record(F, f'portfolio create rejects {label} with a controlled 4xx', 400 <= r.status_code < 500, '4xx', r.status_code, sev='P2')
        r = c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': a.sub.sub_category_id}, format='multipart')
        record(F, 'portfolio create without a file -> 400', r.status_code == 400, 400, r.status_code)
        # 20-item cap
        for i in range(21):
            mk()
        record(F, 'portfolio capped at 20 active items', Portfolio.objects.filter(artist=a.profile, is_active=True, is_work_sample=False).count() == 20, 20, Portfolio.objects.filter(artist=a.profile, is_active=True, is_work_sample=False).count(), sev='P2')

    def test_upload_security(self):
        c, a = self.art.client, self.art
        url = '/artists/profile/photo/upload/'
        png = w.png_bytes()
        def attempt(label, name, content, ctype, should_reject=True, url=url, field='profile_photo', extra=None, sev='P1'):
            r = _upload(c, url, name, content, ctype, extra=extra, field=field, method='put' if 'photo' in url else 'post')
            ok = (r.status_code in (400, 413, 415)) if should_reject else is_2xx(r)
            record('UPLOAD', label, ok and r.status_code != 500, 'rejected' if should_reject else 'accepted', r.status_code, sev=sev)
            return r
        attempt('valid PNG accepted', 'ok.png', png, 'image/png', should_reject=False)
        attempt('HTML renamed .png rejected', 'x.png', b'<html><script>alert(1)</script></html>', 'image/png')
        attempt('PHP with PNG body but .php extension rejected', 'shell.php', png, 'image/png')
        attempt('PNG body with .jpg extension (type mismatch) rejected', 'x.jpg', png, 'image/jpeg')
        attempt('SVG with script rejected', 'x.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'image/svg+xml')
        buf = io.BytesIO(); Image.new('RGB', (4, 4)).save(buf, 'GIF')
        attempt('GIF (not allowed) rejected', 'x.gif', buf.getvalue(), 'image/gif')
        attempt('empty file rejected', 'e.png', b'', 'image/png')
        attempt('truncated PNG header rejected', 't.png', png[:20], 'image/png')
        attempt('random bytes with image MIME rejected', 'r.png', os.urandom(2048), 'image/png')
        attempt('oversize (>5 MB) rejected', 'big.png', png + b'0' * (5 * 1024 * 1024 + 10), 'image/png')
        attempt('executable with image extension rejected', 'x.png', b'MZ\x90\x00' + b'\x00' * 100, 'image/png')
        bomb = io.BytesIO(); Image.new('1', (16000, 16000), 1).save(bomb, 'PNG')
        attempt('decompression-bomb dimensions (16000x16000) rejected without crashing', 'bomb.png', bomb.getvalue(), 'image/png')
        # polyglot: valid PNG with HTML appended
        r = attempt('PNG+HTML polyglot (valid image) is accepted but never served as HTML', 'poly.png', png + b'<script>alert(1)</script>', 'image/png', should_reject=False)
        # path traversal / odd names — must be stored under a random name inside the media root
        for name in ('../../evil.png', '..\\..\\evil.png', 'a' * 250 + '.png', 'ünï©ode.png', 'nul\x00.png'):
            try:
                r = _upload(c, url, name, png, 'image/png', field='profile_photo', method='put')
            except Exception as exc:                       # the client itself refusing is also fine
                record('UPLOAD', f'odd filename {name[:20]!r} handled', True, 'rejected or safely stored', f'client refused: {type(exc).__name__}', sev='P1')
                continue
            from sunndari_apps.artists.models import ArtistProfile
            stored = ArtistProfile.objects.get(artist_id=a.profile.artist_id).profile_photo.name
            full = os.path.realpath(os.path.join(settings.MEDIA_ROOT, stored))
            inside = full.startswith(os.path.realpath(settings.MEDIA_ROOT) + os.sep)
            safe = (r.status_code in (400, 415)) or (is_2xx(r) and inside and '..' not in stored and stored.startswith('artist_photos/'))
            record('UPLOAD', f'filename {name[:24]!r}: rejected or stored safely inside MEDIA_ROOT under a random name', safe and r.status_code != 500, 'safe', f'{r.status_code} -> {stored}', sev='P0')
        # KYC + ticket uploads obey the same validation
        kyc = '/artists/documents/create/'
        base = {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567'}
        r = _upload(c, kyc, 'x.html', b'<script>', 'text/html', extra=base)
        record('UPLOAD', 'KYC rejects HTML', r.status_code == 400, 400, r.status_code, sev='P0')
        r = _upload(c, kyc, 'ok.pdf', b'%PDF-1.4\n%x', 'application/pdf', extra=base)
        record('UPLOAD', 'KYC accepts a real PDF', is_2xx(r), 'accepted', r.status_code, sev='P2')
        doc = ArtistDocument.objects.filter(artist=a.profile).first()
        if doc:
            private = os.path.realpath(os.path.join(settings.PRIVATE_MEDIA_ROOT, doc.file.name))
            record('UPLOAD', 'KYC file is stored outside the public MEDIA_ROOT', private.startswith(os.path.realpath(settings.PRIVATE_MEDIA_ROOT)) and not os.path.exists(os.path.join(settings.MEDIA_ROOT, doc.file.name)), 'private storage only', doc.file.name, sev='P0')
            try:
                doc.file.url
                record('UPLOAD', 'KYC file has no public URL', False, 'url raises', 'url produced', sev='P0')
            except ValueError:
                record('UPLOAD', 'KYC file has no public URL', True, 'url raises', 'raises')
            r = c.get('/artists/documents/file/', {'document_id': doc.document_id})
            record('UPLOAD', 'KYC owner download returns the file with nosniff and no-store', r.status_code == 200 and r['X-Content-Type-Options'] == 'nosniff' and 'no-store' in r['Cache-Control'], 'safe headers', dict(r.headers), sev='P1')
        unverified('UPLOAD', 'public media (portfolio/profile photos) reachable by URL in production', 'Served by Django static() only when DEBUG; the production web-server mapping is not in the repo', sev='P2')

    def test_package_lifecycle_and_booking_integrity(self):
        c, a, cus = self.art.client, self.art, self.cus
        mk = lambda **kw: c.post('/artists/packages/create/', {'sub_category_id': a.sub.sub_category_id, 'name': 'QA pkg', 'price': '1000', 'duration_minutes': 60, **kw}, format='json')
        r = mk(makeup_type='HD', brands=['MAC', 'Huda'], product_details='Airbrush')
        pid = (data(r) or {}).get('package_id')
        record(F, 'package create with extras', r.status_code == 201 and pid, 201, r.status_code, sev='P1')
        g = data(c.get('/artists/packages/get/', {'package_id': pid})) or {}
        record(F, 'package extras persisted and category derived', g.get('makeupType') == 'HD' and g.get('brands') == ['MAC', 'Huda'] and g.get('category', {}).get('name') == 'QA Makeup', 'persisted', g, sev='P1')
        for label, kw in {'price below minimum (499)': {'price': '499'}, 'negative price': {'price': '-5'}, 'zero duration': {'duration_minutes': 0},
                          'text price': {'price': 'cheap'}, 'price too many digits': {'price': '123456789012'}, 'missing name': {'name': ''},
                          'name too long': {'name': 'x' * 201}}.items():
            r = mk(**kw)
            record(F, f'package create rejects {label} (controlled 4xx)', 400 <= r.status_code < 500, '4xx', r.status_code, sev='P2')
        r = mk(price='500', duration_minutes=1)
        record(F, 'package boundary: minimum price 500 / duration 1 accepted', r.status_code == 201, 201, r.status_code, sev='P3')
        r = mk(duration_minutes=100000)
        observe(F, 'package with an absurd duration (100000 min) is accepted', f'HTTP {r.status_code}: can never be booked (slot would pass midnight)', sev='P3')
        # booking snapshot integrity
        booking_id = (data(w.create_booking(cus, a)) or {}).get('booking_id')
        base_total = Booking.objects.get(booking_id=booking_id).total_amount
        c.put('/artists/packages/update/', {'package_id': a.package.package_id, 'price': '9999', 'name': 'Renamed', 'duration_minutes': 300}, format='json')
        b = Booking.objects.get(booking_id=booking_id)
        record(F, 'editing a package after booking does not rewrite the booking (total/slot)', b.total_amount == base_total and str(b.end_time) == '11:00:00', f'total {base_total}, end 11:00', f'total {b.total_amount}, end {b.end_time}', sev='P1')
        r = c.delete(f'/artists/packages/delete/?package_id={a.package.package_id}')
        exists = Booking.objects.filter(booking_id=booking_id).exists() and PricingPackage.objects.filter(package_id=a.package.package_id).exists()
        record(F, 'deleting a package that has bookings is refused with a clear 4xx and keeps the booking', r.status_code != 500 and (400 <= r.status_code < 500) and exists, 'controlled refusal', f'HTTP {r.status_code}: {body(r).get("message")}', sev='P1',
               note='Booking.package is PROTECT; ideal behaviour is a specific message (or soft-delete), not a generic database error')
        observe(F, 'message shown to the artist when deleting a package that has bookings', body(r).get('message'), sev='P3')
        r = c.put('/artists/packages/update/', {'package_id': a.package.package_id, 'is_active': False}, format='json')
        record(F, 'deactivating a package keeps existing bookings and blocks new ones', Booking.objects.filter(booking_id=booking_id).exists() and w.create_booking(w.make_customer('+919400000050', 'Late'), a, start='14:00:00').status_code == 400, 'booking kept, new refused', 'checked', sev='P1')
        r = c.put('/artists/packages/update/', {'package_id': a.package.package_id, 'is_active': True, 'price': '1500', 'name': 'Restored', 'duration_minutes': 60}, format='json')



class ForeignKeyHandlingQA(TransactionTestCase):
    """TestCase hides FK violations until the test ends; TransactionTestCase enforces them at
    commit like production (autocommit) does, so this shows what a real client would see."""

    def tearDown(self):
        dump()

    def test_dangling_foreign_keys_from_the_client(self):
        w.seed_statuses()
        art = w.make_bookable_artist('+919400000101', 'FK Artist')
        c = art.client
        from sunndari_apps.artists.models import Portfolio, PricingPackage
        r = c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': 999999, 'file': w.png()}, format='multipart')
        record('INTEGRITY', 'portfolio with a non-existent sub_category is refused', 400 <= r.status_code < 500 and not Portfolio.objects.filter(sub_category_id=999999).exists(),
               '4xx and nothing stored', f'HTTP {r.status_code}: {body(r).get("message")}; rows={Portfolio.objects.filter(sub_category_id=999999).count()}', sev='P2')
        observe('INTEGRITY', 'error text for the portfolio FK failure', body(r).get('message'), sev='P3', note='Common.exception_handler maps any "foreign key constraint" error to the DELETE message')
        r = c.post('/artists/packages/create/', {'sub_category_id': 999999, 'name': 'x', 'price': '1000', 'duration_minutes': 60}, format='json')
        record('INTEGRITY', 'package with a non-existent sub_category is refused', 400 <= r.status_code < 500 and not PricingPackage.objects.filter(sub_category_id=999999).exists(),
               '4xx and nothing stored', f'HTTP {r.status_code}: {body(r).get("message")}', sev='P2')
        r = c.post('/artists/services/add/', {'sub_category_id': 999999}, format='json')
        record('INTEGRITY', 'service offering with a non-existent sub_category is refused', 400 <= r.status_code < 500, '4xx', f'HTTP {r.status_code}', sev='P2')
        cus = w.make_customer('+919400000102', 'FK Customer')
        r = w.create_booking(cus, art)
        record('INTEGRITY', 'control: a valid booking still works under real transaction semantics', r.status_code == 201, 201, r.status_code, sev='P1')
        r = cus.client.post('/customers/bookings/create/', {'artist_id': art.profile.artist_id, 'package_id': art.package.package_id, 'location_type_id': 999999,
                                                           'booking_date': w.fmt_date(w.future_date(4)), 'start_time': '10:00:00'}, format='json')
        record('INTEGRITY', 'booking with a non-existent location type is refused', 400 <= r.status_code < 500, '4xx', f'HTTP {r.status_code}: {body(r).get("message")}', sev='P2')
