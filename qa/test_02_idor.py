from django.test import TestCase

from sunndari_apps.artists.models import Portfolio, PricingPackage, PackageAddOn, ArtistServiceArea, ArtistDocument, ArtistPayoutAccount, ArtistAvailabilityBlock, ArtistClientNote
from sunndari_apps.customers.models import Booking, Review
from sunndari_apps.help_center.models import SupportTicket, SupportTicketAttachment
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.users.models.customer_address import CustomerAddress
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client
from qa import world as w

F = 'AUTHZ/IDOR'


class IdorQA(TestCase):
    @classmethod
    def setUpTestData(cls):
        w.seed_statuses()
        cls.art_a = w.make_bookable_artist('+919200000001', 'Artist A')
        cls.art_b = w.make_bookable_artist('+919200000002', 'Artist B')
        cls.cus_a = w.make_customer('+919200000011', 'Customer A')
        cls.cus_b = w.make_customer('+919200000012', 'Customer B')
        cls.admin = w.make_admin('+919200000099')

    def tearDown(self):
        dump()

    def _refused(self, label, resp, sev='P0', verify=None):
        """A cross-user attempt must be refused (non-2xx, never 500) AND leave the data untouched."""
        refused = not is_2xx(resp) and resp.status_code != 500
        intact = True if verify is None else verify()
        record(F, label, refused and intact, 'rejected, data untouched', f'HTTP {resp.status_code}, intact={intact}', sev=sev)

    def test_artist_resources(self):
        A, B, CB = self.art_a, self.art_b, self.cus_b
        # --- portfolio
        r = A.client.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': A.sub.sub_category_id, 'caption': 'mine', 'file': w.png()}, format='multipart')
        pid = data(r)['portfolio_id']
        for who, c in (('Artist B', B.client), ('Customer B', CB.client)):
            self._refused(f'{who} cannot GET artist A portfolio item', c.get('/artists/portfolio/get/', {'portfolio_id': pid}))
            self._refused(f'{who} cannot EDIT artist A portfolio item', c.put('/artists/portfolio/update/', {'portfolio_id': pid, 'caption': 'hacked'}, format='json'),
                          verify=lambda: Portfolio.objects.get(portfolio_id=pid).caption == 'mine')
            self._refused(f'{who} cannot DELETE artist A portfolio item', c.delete(f'/artists/portfolio/delete/?portfolio_id={pid}'),
                          verify=lambda: Portfolio.objects.filter(portfolio_id=pid).exists())
        self._refused('Artist B cannot REORDER using artist A portfolio ids', B.client.put('/artists/portfolio/reorder/', {'portfolio_ids': [pid]}, format='json'))
        # --- package
        pkg = A.package.package_id
        for who, c in (('Artist B', B.client), ('Customer B', CB.client)):
            self._refused(f'{who} cannot GET artist A package', c.get('/artists/packages/get/', {'package_id': pkg}))
            self._refused(f'{who} cannot EDIT artist A package', c.put('/artists/packages/update/', {'package_id': pkg, 'name': 'hacked', 'price': '600'}, format='json'),
                          verify=lambda: PricingPackage.objects.get(package_id=pkg).name != 'hacked')
            self._refused(f'{who} cannot DELETE artist A package', c.delete(f'/artists/packages/delete/?package_id={pkg}'),
                          verify=lambda: PricingPackage.objects.filter(package_id=pkg).exists())
        self._refused('Artist B cannot upload a photo to artist A package', B.client.put('/artists/packages/photo/upload/', {'package_id': pkg, 'photo': w.png()}, format='multipart'),
                      verify=lambda: not PricingPackage.objects.get(package_id=pkg).photo)
        # --- add-on
        addon = data(A.client.post('/artists/addons/create/', {'name': 'Hair', 'price': '300', 'package_ids': [pkg]}, format='json'))['addon_id']
        self._refused('Artist B cannot read artist A add-on', B.client.get('/artists/addons/get/', {'addon_id': addon}))
        self._refused('Artist B cannot edit artist A add-on', B.client.put('/artists/addons/update/', {'addon_id': addon, 'name': 'x'}, format='json'),
                      verify=lambda: PackageAddOn.objects.get(addon_id=addon).name == 'Hair')
        self._refused('Artist B cannot delete artist A add-on', B.client.delete(f'/artists/addons/delete/?addon_id={addon}'),
                      verify=lambda: PackageAddOn.objects.filter(addon_id=addon).exists())
        pkg_b = B.package.package_id
        self._refused('Artist A cannot attach artist B package to an own add-on', A.client.post('/artists/addons/create/', {'name': 'x', 'price': '10', 'package_ids': [pkg_b]}, format='json'))
        self._refused('Artist A cannot re-link own add-on to artist B package', A.client.put('/artists/addons/update/', {'addon_id': addon, 'package_ids': [pkg_b]}, format='json'))
        # --- service area
        area = data(A.client.post('/artists/service_areas/add/', {'city': 'Lucknow', 'travel_charge_type': 'free'}, format='json'))['area_id']
        self._refused('Artist B cannot edit artist A service area', B.client.put('/artists/service_areas/update/', {'area_id': area, 'city': 'Hacked'}, format='json'),
                      verify=lambda: ArtistServiceArea.objects.get(area_id=area).city == 'Lucknow')
        self._refused('Artist B cannot remove artist A service area', B.client.delete(f'/artists/service_areas/remove/?area_id={area}'),
                      verify=lambda: ArtistServiceArea.objects.filter(area_id=area).exists())
        # --- KYC document
        r = A.client.post('/artists/documents/create/', {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567', 'file': w.png()}, format='multipart')
        did = data(r)['document_id']
        for who, c in (('Artist B', B.client), ('Customer B', CB.client)):
            self._refused(f'{who} cannot GET artist A KYC document', c.get('/artists/documents/get/', {'document_id': did}))
            self._refused(f'{who} cannot DOWNLOAD artist A KYC file', c.get('/artists/documents/file/', {'document_id': did}))
            self._refused(f'{who} cannot DELETE artist A KYC document', c.delete(f'/artists/documents/delete/?document_id={did}'),
                          verify=lambda: ArtistDocument.objects.filter(document_id=did).exists())
        self._refused('Anonymous cannot download artist A KYC file', new_client().get('/artists/documents/file/', {'document_id': did}))
        listing = B.client.get('/artists/documents/get_all/')
        record(F, 'Artist B document list never contains artist A documents', did not in [d['documentId'] for d in (data(listing) or {}).get('data', [])], 'excluded', listing.status_code, sev='P0')
        self._refused('Customer cannot use admin KYC list', CB.client.get('/admin-panel/artists/documents/get_all/', {'artist_id': A.profile.artist_id}))
        self._refused('Artist B cannot use admin KYC list', B.client.get('/admin-panel/artists/documents/get_all/', {'artist_id': A.profile.artist_id}))
        self._refused('Artist B cannot verify artist A KYC document', B.client.put('/admin-panel/artists/documents/verify/', {'document_id': did, 'decision': 'approved'}, format='json'),
                      verify=lambda: ArtistDocument.objects.get(document_id=did).verification_status.name == 'pending')
        # --- bank
        A.client.put('/artists/payout_account/set/', {'account_holder_name': 'A Holder', 'bank_account_number': '111122223333', 'ifsc_code': 'HDFC0001234'}, format='json')
        rb = B.client.get('/artists/payout_account/get/')
        record(F, 'Artist B payout GET never returns artist A account', rb.status_code != 200 or 'A Holder' not in str(body(rb)), 'no A data', rb.status_code, sev='P0')
        rc = CB.client.get('/artists/payout_account/get/')
        record(F, 'Customer cannot read any payout account', not is_2xx(rc), 'rejected', rc.status_code, sev='P0')
        B.client.put('/artists/payout_account/set/', {'account_holder_name': 'B Holder', 'bank_account_number': '999988887777', 'ifsc_code': 'ICIC0001234'}, format='json')
        record(F, "Artist B setting a payout account does not overwrite artist A's", ArtistPayoutAccount.objects.get(artist=A.profile).account_holder_name == 'A Holder', 'A unchanged', 'checked', sev='P0')
        record(F, 'Payout GET response never exposes the full account number', '111122223333' not in str(body(A.client.get('/artists/payout_account/get/'))), 'masked only', 'checked', sev='P0')
        # --- availability (own-scoped by design: no id parameter)
        A.client.post('/artists/availability/block/add/', {'block_date': '2031-01-05'}, format='json')
        B.client.delete('/artists/availability/block/remove/?block_date=2031-01-05')
        record(F, "Artist B removing a block date never removes artist A's block", ArtistAvailabilityBlock.objects.filter(artist=A.profile).exists(), 'A block kept', 'checked', sev='P1')
        before = A.profile.availability_schedules.count() if hasattr(A.profile, 'availability_schedules') else None
        B.client.delete('/artists/availability/schedule/remove/?day_of_week=1')
        from sunndari_apps.artists.models import ArtistAvailabilitySchedule
        record(F, "Artist B removing a weekday schedule never touches artist A's", ArtistAvailabilitySchedule.objects.filter(artist=A.profile, day_of_week=1, is_active=True).exists(), 'A schedule kept', 'checked', sev='P1')
        # --- foreign lists
        r = CB.client.get('/artists/packages/get_all/', {'artist_id': A.profile.artist_id})
        record(F, 'Public package list of an approved artist is readable (intended)', r.status_code == 200, 200, r.status_code, sev='P3')

    def test_customer_and_cross_role(self):
        A, B, CA, CB = self.art_a, self.art_b, self.cus_a, self.cus_b
        # --- address
        addr = CA.address.address_id
        self._refused('Customer B cannot GET customer A address', CB.client.get('/users/address/get/', {'address_id': addr}))
        self._refused('Customer B cannot EDIT customer A address', CB.client.put('/users/address/update/', {'address_id': addr, 'city': 'Hacked'}, format='json'),
                      verify=lambda: CustomerAddress.objects.get(address_id=addr).city == 'Lucknow')
        self._refused('Customer B cannot DELETE customer A address', CB.client.delete(f'/users/address/delete/?address_id={addr}'),
                      verify=lambda: CustomerAddress.objects.filter(address_id=addr).exists())
        listed = CB.client.get('/users/address/get_all/')
        record(F, 'Customer B address list excludes customer A addresses', addr not in [a['addressId'] for a in (data(listed) or {}).get('data', [])], 'excluded', listed.status_code, sev='P0')
        # --- profile of another user (PII)
        r = CB.client.get('/users/profile/get/', {'user_id': CA.id})
        payload = data(r) or {}
        leaked_token = CA.token in str(body(r))
        record(F, "Customer B sees no private data (phone/email/tokens) of customer A - at most a name/role label", set(payload) <= {'userId', 'name', 'role'} and 'email' not in payload, 'only userId/name/role', f'HTTP {r.status_code}; keys={sorted(payload)[:12]}', sev='P0',
               note='users/profile/get takes an arbitrary user_id; after the fix other users get a minimal label')
        record(F, "Another user's access token is never present in any profile response", not leaked_token, 'absent', f'token leaked={leaked_token}', sev='P0')
        record(F, "Another user's FCM/device token is never exposed", 'fcmToken' not in payload and 'fcm_token' not in payload, 'absent', sorted(payload), sev='P1')
        ra = CB.client.get('/users/profile/get/', {'user_id': A.id})
        observe(F, 'Customer can read an artist user profile by id', f'HTTP {ra.status_code}: {sorted(data(ra) or {})}', sev='P3')
        # --- booking isolation
        bid = w.confirmed_booking(CA, A)
        tests = [
            ('Artist B cannot GET artist A booking', B.client.get('/artists/bookings/get/', {'booking_id': bid})),
            ('Artist B cannot update status of artist A booking', B.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled', 'reason': 'x'}, format='json')),
            ('Artist B cannot mark on-my-way for artist A booking', B.client.put('/artists/bookings/on_my_way/', {'booking_id': bid}, format='json')),
            ('Artist B cannot confirm arrival for artist A booking', B.client.put('/artists/bookings/arrived/', {'booking_id': bid, 'booking_otp': 123456}, format='json')),
            ('Artist B cannot verify start PIN for artist A booking', B.client.put('/artists/bookings/start_pin/verify/', {'booking_id': bid, 'start_service_pin': 1234}, format='json')),
            ('Artist B cannot verify completion PIN for artist A booking', B.client.put('/artists/bookings/completion_pin/verify/', {'booking_id': bid, 'completion_pin': 1234}, format='json')),
            ('Customer B cannot GET customer A booking', CB.client.get('/customers/bookings/get/', {'booking_id': bid})),
            ('Customer B cannot CANCEL customer A booking', CB.client.put('/customers/bookings/cancel/', {'booking_id': bid}, format='json')),
            ('Customer B cannot read customer A start PIN', CB.client.get('/customers/bookings/start_pin/', {'booking_id': bid})),
            ('Customer B cannot read customer A completion PIN', CB.client.get('/customers/bookings/completion_pin/', {'booking_id': bid})),
            ('Customer A cannot use artist status endpoint on own booking', CA.client.put('/artists/bookings/update_status/', {'booking_id': bid, 'status': 'cancelled'}, format='json')),
            ('Customer B cannot request a reschedule', CB.client.post('/artists/bookings/reschedule/request/', {'booking_id': bid, 'proposed_date': '01-01-40', 'proposed_start_time': '10:00:00'}, format='json')),
            ('Artist B cannot request a reschedule of artist A booking', B.client.post('/artists/bookings/reschedule/request/', {'booking_id': bid, 'proposed_date': w.fmt_date(w.future_date(4)), 'proposed_start_time': '12:00:00'}, format='json')),
            ('Customer B cannot review customer A booking', CB.client.post('/customers/reviews/create/', {'booking_id': bid, 'rating': 5}, format='json')),
            ('Artist B cannot rate customer A after artist A booking', B.client.post('/artists/customer_reviews/create/', {'booking_id': bid, 'rating': 1}, format='json')),
            ('Artist B cannot open chat for artist A booking', B.client.get('/chat/conversation/get/', {'booking_id': bid})),
            ('Customer B cannot open chat for customer A booking', CB.client.get('/chat/conversation/get/', {'booking_id': bid})),
            ('Customer B cannot post chat on customer A booking', CB.client.post('/chat/messages/create/', {'booking_id': bid, 'content': 'hello'}, format='json')),
            ('Artist B cannot read chat of artist A booking', B.client.get('/chat/messages/get_all/', {'booking_id': bid})),
        ]
        for label, resp in tests:
            self._refused(label, resp)
        record(F, 'Booking untouched after all cross-user attempts', Booking.objects.get(booking_id=bid).status.name == 'confirmed', 'confirmed', Booking.objects.get(booking_id=bid).status.name, sev='P0')
        # --- notifications
        note = Notification.objects.filter(user_id=CA.id).first() or Notification.objects.filter(user_id=A.id).first()
        owner = CA if note and note.user_id == CA.id else A
        other = CB if owner is CA else B
        if note:
            self._refused('Another user cannot read a notification', other.client.get('/notifications/get/', {'notification_id': note.notification_id}))
            self._refused('Another user cannot mark a notification read', other.client.put('/notifications/mark_read/', {'notification_id': note.notification_id}, format='json'),
                          verify=lambda: not Notification.objects.get(notification_id=note.notification_id).is_read)
        feed = CB.client.get('/notifications/get_all/')
        record(F, "Customer B notification feed excludes other users' notifications", all(n.get('userId') in (None, CB.id) for n in (data(feed) or {}).get('data', [])) , 'only own', feed.status_code, sev='P0')
        # --- reviews / client notes
        self._refused('Artist B cannot add a private note for a customer who never booked them', B.client.put('/artists/clients/note/set/', {'customer_id': CA.id, 'note': 'x'}, format='json'),
                      verify=lambda: not ArtistClientNote.objects.filter(artist=B.profile).exists())
        # --- tickets
        t = data(CA.client.post('/help_center/tickets/create/', {'issue_type': 'payment', 'subject': 'S', 'description': 'D', 'attachments': w.png()}, format='multipart'))['ticket_id']
        att = SupportTicketAttachment.objects.get(ticket_id=t).attachment_id
        self._refused('Customer B cannot read customer A ticket', CB.client.get('/help_center/tickets/get/', {'ticket_id': t}))
        self._refused('Customer B cannot download customer A ticket attachment', CB.client.get('/help_center/tickets/attachment/', {'attachment_id': att}))
        self._refused('Customer B cannot close customer A ticket', CB.client.put('/help_center/tickets/close/', {'ticket_id': t}, format='json'),
                      verify=lambda: SupportTicket.objects.get(ticket_id=t).status == 'open')
        self._refused('Customer cannot use admin ticket list', CA.client.get('/help_center/admin/tickets/get_all/'))
        self._refused('Customer cannot change ticket status', CA.client.put('/help_center/admin/tickets/update_status/', {'ticket_id': t, 'status': 'resolved'}, format='json'),
                      verify=lambda: SupportTicket.objects.get(ticket_id=t).status == 'open')
        # --- help-center chat isolation
        CA.client.post('/help_center/messages/create/', {'content': 'private question'}, format='json')
        mb = CB.client.get('/help_center/messages/get_all/')
        record(F, "Customer B help-center chat never shows customer A's messages", 'private question' not in str(body(mb)), 'isolated', mb.status_code, sev='P0')
        ma = A.client.get('/help_center/messages/get_all/')
        record(F, "Help-center customer route does not expose conversations to artist role incorrectly", 'private question' not in str(body(ma)), 'isolated', ma.status_code, sev='P0')
