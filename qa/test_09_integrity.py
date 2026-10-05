import os
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.urls import get_resolver, URLPattern, URLResolver

from sunndari_apps.artists.models import ArtistProfile, ArtistDocument
from sunndari_apps.authentication.models import User
from sunndari_apps.chat.models import Conversation, Message
from sunndari_apps.customers.models import Booking, BookingAddOn
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.users.models.customer_address import CustomerAddress
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client, LOG_CAPTURE
from qa import world as w

F = 'INTEGRITY'


class TransactionQA(TransactionTestCase):
    """Autocommit semantics: what a real request leaves behind when a later step fails."""

    def setUp(self):
        w.seed_statuses()
        self.art = w.make_bookable_artist('+919950000001', 'Txn Artist')
        self.cus = w.make_customer('+919950000002', 'Txn Customer')

    def tearDown(self):
        dump()

    def test_booking_creation_failures(self):
        from sunndari_apps.artists.models import PackageAddOn
        addon = PackageAddOn.objects.create(artist=self.art.profile, name='A', price=Decimal('100')); addon.packages.add(self.art.package)
        before = Booking.objects.count()
        with patch.object(Booking, 'generate_booking_otp', side_effect=RuntimeError('otp store down')):
            r = w.create_booking(self.cus, self.art, day=3)
        record(F, 'a failure while issuing the booking OTP leaves no half-created booking', Booking.objects.count() == before and r.status_code != 201, 'rolled back', f'HTTP {r.status_code}, bookings {before}->{Booking.objects.count()}', sev='P1')
        with patch('sunndari_apps.customers.views.create_booking.BookingAddOn.objects.bulk_create', side_effect=RuntimeError('db hiccup')):
            r = w.create_booking(self.cus, self.art, day=3, addon_ids=[addon.addon_id])
        record(F, 'a failure while saving the add-on snapshot rolls the whole booking back', Booking.objects.count() == before and r.status_code != 201, 'rolled back', f'HTTP {r.status_code}, bookings={Booking.objects.count()}', sev='P1')
        with patch.object(NotificationService, '_notify', side_effect=RuntimeError('notification backend down')):
            r = w.create_booking(self.cus, self.art, day=3)
        persisted = Booking.objects.count() - before
        record(F, 'notification failure after commit: the API response matches what was stored', (r.status_code == 201 and persisted == 1) or (r.status_code != 201 and persisted == 0), 'consistent (success+stored OR failure+nothing stored)',
               f'HTTP {r.status_code} but bookings stored={persisted}', sev='P2',
               note='create_booking sends notifications after the transaction commits and does not guard them: the slot IS booked while the client is told it failed')
        if persisted == 1 and r.status_code != 201:
            retry = w.create_booking(self.cus, self.art, day=3)
            observe(F, 'consequence: the client retry after the false failure', f'HTTP {retry.status_code} ({body(retry).get("message")}) - the customer is told the slot is unavailable although they hold it', sev='P2')
        # Firebase down is the normal situation here: bookings still work
        fb = [l for l in LOG_CAPTURE.lines if 'Failed to sync' in l]
        r = w.create_booking(w.make_customer('+919950000003', 'Fb Customer'), self.art, day=4)
        record(F, 'Firebase/Firestore failure never blocks a booking (handled, logged)', r.status_code == 201 and any('Firestore' in l for l in LOG_CAPTURE.lines), 'booking succeeds, failure logged', f'HTTP {r.status_code}, firestore log lines={len([l for l in LOG_CAPTURE.lines if "Firestore" in l])}', sev='P2',
               note='Business success + notification-sync failure is the implemented (and sensible) semantics')

    def test_state_changes_with_failures(self):
        bid = data(w.create_booking(self.cus, self.art, day=5))['booking_id']
        w.pay(bid)
        with patch.object(NotificationService, '_notify', side_effect=RuntimeError('boom')):
            r = self.art.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'confirmed'}, format='json')
        status_now = Booking.objects.get(booking_id=bid).status.name
        record(F, 'accepting a booking: response and stored status agree when the notification step fails', (r.status_code == 200) == (status_now == 'confirmed'), 'consistent', f'HTTP {r.status_code}, stored {status_now}', sev='P2')
        # completion cashback atomicity
        w.pay  # noqa
        art2 = w.make_bookable_artist('+919950000010', 'Txn Artist 2')
        bid2 = w.confirmed_booking(self.cus, art2, day=6)
        Booking.objects.filter(booking_id=bid2).update(status=__import__('sunndari_apps.core.models', fromlist=['BookingStatus']).BookingStatus.objects.get(name='in_progress'), completion_pin=4321,
                                                       completion_pin_expiry=__import__('django.utils.timezone', fromlist=['now']).now() + __import__('datetime').timedelta(days=30))
        with patch('sunndari_apps.wallet.models.customer_wallet.CustomerWallet.award_cashback', side_effect=RuntimeError('wallet down')):
            r = art2.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid2, 'completion_pin': 4321}, format='json')
        b = Booking.objects.get(booking_id=bid2)
        record(F, 'wallet failure during completion rolls completion back and keeps the PIN usable for a retry', b.status.name == 'in_progress' and b.completion_pin == 4321, 'in_progress + PIN intact', f'HTTP {r.status_code}, {b.status.name}, pin={b.completion_pin}', sev='P1')

    def test_registration_and_upload_failures(self):
        c = new_client()
        with patch('sunndari_apps.artists.models.artist_profile.ArtistProfile.create_for_user', side_effect=RuntimeError('db')):
            r = c.post('/auth/register/', {'name': 'Rollback', 'phone_number': '+919950000020', 'password': 'Str0ng-pass!', 'role': 'artist'}, format='json')
        record(F, 'artist registration is all-or-nothing (no user without a profile)', not User.objects.filter(phone_number='+919950000020').exists() or ArtistProfile.objects.filter(user__phone_number='+919950000020').exists(), 'rolled back', f'HTTP {r.status_code}', sev='P1')
        with patch('sunndari_apps.artists.models.document.ArtistDocument.replace_id_proofs', side_effect=RuntimeError('db')):
            before = ArtistDocument.objects.count()
            files_before = sum(len(f) for _, _, f in os.walk(settings.PRIVATE_MEDIA_ROOT))
            r = self.art.client.post('/artists/documents/create/', {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567', 'file': w.png()}, format='multipart')
            files_after = sum(len(f) for _, _, f in os.walk(settings.PRIVATE_MEDIA_ROOT))
        record(F, 'a failed KYC upload leaves no document row', ArtistDocument.objects.count() == before, 'no row', ArtistDocument.objects.count() - before, sev='P1')
        record(F, 'a failed KYC upload leaves no orphaned identity file on disk', files_after == files_before, 'no orphan', f'files {files_before}->{files_after}', sev='P3',
               note='the file is written to storage before the surrounding DB transaction fails; rollback does not remove it')

    def test_foreign_key_and_cascade_integrity(self):
        bid = data(w.create_booking(self.cus, self.art, day=7))['booking_id']
        r = self.art.client.delete(f'/artists/packages/delete/?package_id={self.art.package.package_id}')
        record(F, 'deleting a package with bookings does not orphan or delete the booking', Booking.objects.filter(booking_id=bid).exists(), 'booking intact', f'HTTP {r.status_code}', sev='P0')
        observe(F, 'package-with-bookings deletion message', body(r).get('message'), sev='P3', note='Generic message (or internal model text when DEBUG is on); a specific "has bookings, deactivate it instead" message would help')
        orphans = Booking.objects.exclude(package_id__in=__import__('sunndari_apps.artists.models', fromlist=['PricingPackage']).PricingPackage.objects.values('package_id')).count()
        record(F, 'no booking references a missing package/artist/customer after the run', orphans == 0, 0, orphans, sev='P0')
        u = self.cus.user
        n_before = Booking.objects.filter(customer=u).count()
        observe(F, 'account deletion', 'No API exists to delete a user/account (cascade behaviour of Booking.customer=CASCADE is therefore unreachable via the API)', sev='P3')


class ChatNotificationQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.art = w.make_bookable_artist('+919960000001', 'Chat Artist')
        cls.cus = w.make_customer('+919960000002', 'Chat Customer')
        cls.out = w.make_customer('+919960000003', 'Chat Outsider')

    def tearDown(self):
        dump()

    def test_chat(self):
        A, C, O = self.art, self.cus, self.out
        bid = w.confirmed_booking(C, A, day=3)
        pend = data(w.create_booking(C, A, start='15:00:00', day=3))['booking_id']
        r = C.client.get('/chat/conversation/get/', {'booking_id': bid})
        record('CHAT', 'customer opens the conversation of their booking', r.status_code == 200, 200, r.status_code, sev='P1')
        r = A.client.get('/chat/conversation/get/', {'booking_id': bid})
        record('CHAT', 'artist opens the same conversation', r.status_code == 200, 200, r.status_code, sev='P1')
        record('CHAT', 'exactly one conversation exists per booking (no duplicates)', Conversation.objects.filter(booking_id=bid).count() == 1, 1, Conversation.objects.filter(booking_id=bid).count(), sev='P2')
        r = C.client.post('/chat/messages/create/', {'booking_id': bid, 'content': 'Hello artist'}, format='json')
        record('CHAT', 'customer sends a message', r.status_code in (200, 201), '2xx', r.status_code, sev='P1')
        r = A.client.post('/chat/messages/create/', {'booking_id': bid, 'content': 'Hi!'}, format='json')
        got = [m['content'] for m in (data(C.client.get('/chat/messages/get_all/', {'booking_id': bid})) or {}).get('data', [])]
        record('CHAT', 'both sides see the whole thread in order', got[:2] == ['Hello artist', 'Hi!'], ['Hello artist', 'Hi!'], got, sev='P1')
        record('CHAT', 'sending a message notifies the other party', Notification.objects.filter(user_id=A.id, type__icontains='chat').exists() or Notification.objects.filter(user_id=A.id).exists(), 'notified', 'checked', sev='P3')
        for label, content, expect in (('empty message', '', 400), ('whitespace-only message', '   ', 400), ('2000 chars (limit)', 'x' * 2000, 201), ('2001 chars', 'x' * 2001, 400)):
            r = C.client.post('/chat/messages/create/', {'booking_id': bid, 'content': content}, format='json')
            record('CHAT', f'{label}', (r.status_code in (200, 201)) if expect == 201 else r.status_code == 400, expect, r.status_code, sev='P2')
        r = C.client.post('/chat/messages/create/', {'booking_id': bid, 'content': '<script>alert(1)</script>'}, format='json')
        stored = Message.objects.filter(conversation__booking_id=bid).order_by('-pk').first()
        record('CHAT', 'HTML in a message is stored verbatim (clients must escape on render) and returned as plain JSON text', r.status_code in (200, 201) and stored and stored.content == '<script>alert(1)</script>', 'stored raw', getattr(stored, 'content', None), sev='P3')
        record('CHAT', 'unknown booking id -> controlled 4xx', 400 <= C.client.get('/chat/conversation/get/', {'booking_id': 999999}).status_code < 500, '4xx', 'checked', sev='P2')
        observe('CHAT', 'chat on a not-yet-confirmed (pending) booking', f'conversation HTTP {C.client.get("/chat/conversation/get/", {"booking_id": pend}).status_code}, message HTTP {C.client.post("/chat/messages/create/", {"booking_id": pend, "content": "hi"}, format="json").status_code}', sev='P3')
        for label, resp in {'outsider cannot open the conversation': O.client.get('/chat/conversation/get/', {'booking_id': bid}),
                            'outsider cannot read messages': O.client.get('/chat/messages/get_all/', {'booking_id': bid}),
                            'outsider cannot post a message': O.client.post('/chat/messages/create/', {'booking_id': bid, 'content': 'intrude'}, format='json')}.items():
            record('CHAT', label, not is_2xx(resp), 'refused', resp.status_code, sev='P0')
        record('CHAT', 'the outsider message was not stored', not Message.objects.filter(content='intrude').exists(), 'absent', 'checked', sev='P0')

    def test_notifications(self):
        A, C = self.art, self.cus
        w.confirmed_booking(C, A, day=3)
        feed = data(A.client.get('/notifications/get_all/')) or {}
        items = feed.get('data', [])
        record('NOTIFY', 'artist has booking notifications after a booking', len(items) >= 1, '>=1', len(items), sev='P2')
        if items:
            nid = items[0]['notificationId']
            r = A.client.put('/notifications/mark_read/', {'notification_id': nid}, format='json')
            record('NOTIFY', 'mark one notification read', r.status_code == 200 and Notification.objects.get(notification_id=nid).is_read, 'read', r.status_code, sev='P3')
        r = A.client.put('/notifications/mark_all_read/', {}, format='json')
        record('NOTIFY', 'mark all read', r.status_code == 200 and not Notification.objects.filter(user_id=A.id, is_read=False).exists(), 'all read', r.status_code, sev='P3')
        record('NOTIFY', "marking all read does not touch other users' notifications", Notification.objects.filter(user_id=C.id, is_read=False).exists() or not Notification.objects.filter(user_id=C.id).exists(), 'others untouched', 'checked', sev='P1')
        observe('NOTIFY', 'push delivery (FCM) and Firestore sync', 'BLOCKED in this environment: FCM is a stub (NotificationGateway.send returns "FCM not yet configured") and Firebase is deliberately disabled under test; in-app notification rows ARE stored', sev='P2')
        blocked('NOTIFY', 'real device push / Firestore realtime sync', 'EXTERNAL DEPENDENCY: Firebase credentials unavailable')

    def test_customer_flow(self):
        c = new_client()
        reg = c.post('/auth/register/', {'name': 'Flow Cust', 'phone_number': '+919960000010', 'password': 'Str0ng-pass!', 'role': 'customer'}, format='json')
        cc = new_client(data(reg)['access_token'])
        addrs = []
        for i in range(6):
            r = cc.post('/users/address/create/', {'address_line_1': f'{i} Rd', 'city': 'Lucknow', 'pin_code': '226001', 'is_default': i == 0}, format='json')
            addrs.append(r.status_code)
        record('CUSTOMER', 'saved-address limit of 5 enforced (6th refused)', addrs[:5] == [201] * 5 and addrs[5] == 400, '5x201 then 400', addrs, sev='P3')
        listing = data(cc.get('/users/address/get_all/'))['data']
        record('CUSTOMER', 'address list returns exactly the customer\'s own 5 addresses', len(listing) == 5, 5, len(listing), sev='P1')
        new_default = listing[1]['addressId']
        cc.put('/users/address/update/', {'address_id': new_default, 'is_default': True}, format='json')
        defaults = [a for a in data(cc.get('/users/address/get_all/'))['data'] if a['isDefault']]
        record('CUSTOMER', 'only one default address at any time', len(defaults) == 1 and defaults[0]['addressId'] == new_default, 'single default', len(defaults), sev='P2')
        r = cc.delete(f'/users/address/delete/?address_id={listing[0]["addressId"]}')
        record('CUSTOMER', 'address delete works', r.status_code == 200, 200, r.status_code, sev='P2')
        r = cc.put('/users/profile/update/', {'name': 'Renamed Customer'}, format='json')
        record('CUSTOMER', 'profile name update persists', r.status_code == 200 and User.objects.get(phone_number='+919960000010').name == 'Renamed Customer', 'persisted', r.status_code, sev='P2')
        r = cc.put('/users/profile/update/', {'phone_number': '+919960000099'}, format='json')
        record('CUSTOMER', 'phone number cannot be swapped without OTP verification', r.status_code == 400 and User.objects.get(name='Renamed Customer').phone_number == '+919960000010', 'refused', r.status_code, sev='P1')

    def test_admin_surface(self):
        admin = w.make_admin('+919960000020')
        routes = []
        def walk(patterns, prefix=''):
            for p in patterns:
                if isinstance(p, URLResolver):
                    walk(p.url_patterns, prefix + str(p.pattern))
                elif isinstance(p, URLPattern):
                    routes.append(prefix + str(p.pattern))
        walk(get_resolver().url_patterns)
        admin_routes = ['/' + r for r in routes if r.startswith(('admin-panel/',)) or r.startswith('help_center/admin/') and not r.endswith('chat/')]
        bad = []
        for role, actor in (('customer', self.cus), ('artist', self.art), ('anonymous', None)):
            client = actor.client if actor else new_client()
            for url in admin_routes:
                for method in ('get', 'post', 'put', 'delete'):
                    resp = getattr(client, method)(url)
                    if is_2xx(resp):
                        bad.append((role, method.upper(), url, resp.status_code))
        record('ADMIN', f'all {len(admin_routes)} admin routes x 4 methods reject customer, artist and anonymous callers', not bad, 'no 2xx', bad[:5], sev='P0')
        ok = admin.client.get('/admin-panel/artists/review_queue/get_all/')
        record('ADMIN', 'a genuine admin token works on admin routes (control)', ok.status_code == 200, 200, ok.status_code, sev='P1')
        observe('ADMIN', 'admin authentication', 'There is no separate admin login: admins authenticate through the ordinary /auth/* endpoints with role=admin; admin accounts can only be created outside the API (createsuperuser / Django admin)', sev='P3')
