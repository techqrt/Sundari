import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.artists.models import BrandRequest
from sunndari_apps.core.models import Brand
from sunndari_apps.help_center.models import SupportTicket, SupportTicketAttachment
from sunndari_apps.notifications.models.notification import Notification

from tests.test_artists import make_authenticated_client, make_image_bytes
from tests.test_customers import make_customer, make_artist, make_package, make_location_type, make_booking, seed_booking_statuses, next_weekday


def make_admin(phone='+919400000900'):
    return make_authenticated_client(phone_number=phone, role='admin')[0]


class BrandTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.artist, self.artist_user = make_authenticated_client(phone_number='+919000007000')

    def test_admin_manages_the_list_and_everyone_reads_active_brands(self):
        self.assertEqual(self.admin.post('/admin-panel/brands/create/', {'name': 'MAC'}, format='json').status_code, 201)
        hidden_id = self.admin.post('/admin-panel/brands/create/', {'name': 'Old Brand'}, format='json').data['data']['brand_id']
        self.admin.put('/admin-panel/brands/update/', {'brand_id': hidden_id, 'is_active': False}, format='json')
        customer, _ = make_customer(phone_number='+919000007001')
        for client in (self.artist, customer):
            rows = client.get('/core/brands/get_all/').data['data']['data']
            self.assertEqual([r['name'] for r in rows], ['MAC'])
        self.assertEqual(self.artist.get('/core/brands/get_all/', {'search_key': 'zzz'}).data['data']['data'], [])
        self.assertEqual(APIClient().get('/core/brands/get_all/').status_code, 401)

    def test_names_are_unique_case_insensitively(self):
        self.admin.post('/admin-panel/brands/create/', {'name': 'Huda Beauty'}, format='json')
        self.assertEqual(self.admin.post('/admin-panel/brands/create/', {'name': ' huda beauty '}, format='json').status_code, 400)
        other_id = self.admin.post('/admin-panel/brands/create/', {'name': 'Lakme'}, format='json').data['data']['brand_id']
        self.assertEqual(self.admin.put('/admin-panel/brands/update/', {'brand_id': other_id, 'name': 'HUDA BEAUTY'}, format='json').status_code, 400)
        self.assertEqual(self.admin.put('/admin-panel/brands/update/', {'brand_id': other_id, 'name': 'Lakme Pro'}, format='json').status_code, 200)

    def test_only_admins_manage_brands(self):
        self.assertEqual(self.artist.post('/admin-panel/brands/create/', {'name': 'X'}, format='json').status_code, 400)
        self.assertEqual(Brand.objects.count(), 0)
        brand = Brand.objects.create(name='Y')
        self.assertEqual(self.artist.put('/admin-panel/brands/update/', {'brand_id': brand.brand_id, 'is_active': False}, format='json').status_code, 400)
        self.assertTrue(Brand.objects.get(brand_id=brand.brand_id).is_active)
        self.assertEqual(APIClient().post('/admin-panel/brands/create/', {'name': 'X'}, format='json').status_code, 401)

    def test_request_approve_creates_the_brand_and_notifies(self):
        resp = self.artist.post('/artists/brands/request/', {'name': 'Charlotte Tilbury'}, format='json')
        self.assertEqual(resp.status_code, 201)
        request_id = resp.data['data']['request_id']
        pending = self.admin.get('/admin-panel/brands/requests/get_all/', {'filter_key': 'status', 'filter_value': 'pending'}).data['data']['data']
        self.assertEqual([r['name'] for r in pending], ['Charlotte Tilbury'])
        self.assertEqual(self.admin.put('/admin-panel/brands/requests/decide/', {'request_id': request_id, 'decision': 'approved'}, format='json').status_code, 200)
        self.assertTrue(Brand.objects.filter(name='Charlotte Tilbury').exists())
        mine = self.artist.get('/artists/brands/requests/get_all/').data['data']['data']
        self.assertEqual((mine[0]['status'], mine[0]['name']), ('approved', 'Charlotte Tilbury'))
        self.assertTrue(Notification.objects.filter(user_id=self.artist_user.user_id, type='brand_request_approved').exists())
        self.assertEqual(self.admin.put('/admin-panel/brands/requests/decide/', {'request_id': request_id, 'decision': 'rejected'}, format='json').status_code, 400)

    def test_reject_does_not_create_a_brand(self):
        request_id = self.artist.post('/artists/brands/request/', {'name': 'Dodgy'}, format='json').data['data']['request_id']
        self.admin.put('/admin-panel/brands/requests/decide/', {'request_id': request_id, 'decision': 'rejected', 'note': 'Not a real brand'}, format='json')
        self.assertFalse(Brand.objects.exists())
        self.assertEqual(self.artist.get('/artists/brands/requests/get_all/').data['data']['data'][0]['adminNote'], 'Not a real brand')

    def test_request_rules(self):
        Brand.objects.create(name='MAC')
        self.assertEqual(self.artist.post('/artists/brands/request/', {'name': 'mac'}, format='json').status_code, 400)
        self.assertEqual(self.artist.post('/artists/brands/request/', {'name': 'New1'}, format='json').status_code, 201)
        self.assertEqual(self.artist.post('/artists/brands/request/', {'name': 'new1'}, format='json').status_code, 400)
        for i in range(2, 6):
            self.assertEqual(self.artist.post('/artists/brands/request/', {'name': f'New{i}'}, format='json').status_code, 201)
        self.assertEqual(self.artist.post('/artists/brands/request/', {'name': 'New6'}, format='json').status_code, 400)
        customer, _ = make_customer(phone_number='+919000007002')
        self.assertEqual(customer.post('/artists/brands/request/', {'name': 'Zed'}, format='json').status_code, 400)
        self.assertEqual(self.artist.post('/artists/brands/request/', {'name': '  '}, format='json').status_code, 400)

    def test_requests_are_private_and_admin_queue_is_admin_only(self):
        self.artist.post('/artists/brands/request/', {'name': 'Mine'}, format='json')
        other, _ = make_authenticated_client(phone_number='+919000007003')
        self.assertEqual(other.get('/artists/brands/requests/get_all/').data['data']['data'], [])
        self.assertEqual(self.artist.get('/admin-panel/brands/requests/get_all/').status_code, 400)

    def test_approving_a_name_already_added_by_hand_is_not_an_error(self):
        request_id = self.artist.post('/artists/brands/request/', {'name': 'Nykaa'}, format='json').data['data']['request_id']
        Brand.objects.create(name='Nykaa')
        self.assertEqual(self.admin.put('/admin-panel/brands/requests/decide/', {'request_id': request_id, 'decision': 'approved'}, format='json').status_code, 200)
        self.assertEqual(Brand.objects.filter(name__iexact='nykaa').count(), 1)


class StaticPagesTest(TestCase):
    def test_public_and_returns_configured_values_or_null(self):
        resp = APIClient().get('/core/pages/get/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['agreementVersion'], '1.0')
        with patch('sunndari.config.Configurations.terms_url', 'https://sunndari.in/terms'), \
                patch('sunndari.config.Configurations.contact_email', 'help@sunndari.in'):
            data = APIClient().get('/core/pages/get/').data['data']
        self.assertEqual((data['termsUrl'], data['contactEmail']), ('https://sunndari.in/terms', 'help@sunndari.in'))
        self.assertIsNone(data['contactPhone'])

    def test_a_bad_token_does_not_break_it(self):
        self.assertEqual(APIClient().get('/core/pages/get/', HTTP_AUTHORIZATION='Bearer junk').status_code, 200)


class SupportTicketTest(TestCase):
    url = '/help_center/tickets/create/'

    def setUp(self):
        seed_booking_statuses()
        self.artist, self.artist_user, self.profile = make_artist(phone_number='+919000007100')
        self.customer, self.customer_user = make_customer(phone_number='+919000007101')
        self.admin = make_admin('+919400000901')

    def _png(self, name='shot.png'):
        return SimpleUploadedFile(name, make_image_bytes('PNG'), content_type='image/png')

    def _create(self, client=None, files=(), **extra):
        payload = {'issue_type': 'payment', 'subject': 'Charged twice', 'description': 'I was charged two times', **extra}
        if files:
            payload['attachments'] = list(files)
        return (client or self.customer).post(self.url, payload, format='multipart')

    def _booking(self):
        package = make_package(self.profile)
        return make_booking(self.customer_user, self.profile, package, make_location_type('Studio'), next_weekday(2), '10:00', '11:00')

    def test_customer_and_artist_can_both_create_and_see_only_their_own(self):
        a = self._create().data['data']['ticket_id']
        b = self._create(client=self.artist, issue_type='technical', subject='App crash').data['data']['ticket_id']
        self.assertEqual([t['ticketId'] for t in self.customer.get('/help_center/tickets/get_all/').data['data']['data']], [a])
        self.assertEqual([t['ticketId'] for t in self.artist.get('/help_center/tickets/get_all/').data['data']['data']], [b])
        self.assertEqual(self.customer.get('/help_center/tickets/get/', {'ticket_id': b}).status_code, 400)
        data = self.customer.get('/help_center/tickets/get/', {'ticket_id': a}).data['data']
        self.assertEqual((data['status'], data['issueType'], data['bookingId'], data['attachments']), ('open', 'payment', None, []))

    def test_many_tickets_with_booking_and_filters(self):
        booking = self._booking()
        self._create(booking_id=booking.booking_id)
        self._create(issue_type='account', subject='Other thing', description='Cannot log in')
        self.assertEqual(len(self.customer.get('/help_center/tickets/get_all/').data['data']['data']), 2)
        by_booking = self.customer.get('/help_center/tickets/get_all/', {'filter_key': 'bookingId', 'filter_value': booking.booking_id}).data['data']['data']
        self.assertEqual([t['bookingId'] for t in by_booking], [booking.booking_id])
        by_type = self.customer.get('/help_center/tickets/get_all/', {'filter_key': 'issueType', 'filter_value': 'account'}).data['data']['data']
        self.assertEqual([t['subject'] for t in by_type], ['Other thing'])
        found = self.customer.get('/help_center/tickets/get_all/', {'search_key': 'charged'}).data['data']['data']
        self.assertEqual(len(found), 1)

    def test_booking_must_belong_to_the_user(self):
        booking = self._booking()
        stranger, _ = make_customer(phone_number='+919000007102')
        self.assertEqual(self._create(client=stranger, booking_id=booking.booking_id).status_code, 400)
        self.assertEqual(self._create(client=self.artist, booking_id=booking.booking_id).status_code, 201)   # the booking's artist
        self.assertEqual(self._create(booking_id=999999).status_code, 400)

    def test_attachments_validated_limited_and_private(self):
        ok = self._create(files=[self._png('a.png'), self._png('b.png')])
        self.assertEqual(ok.status_code, 201)
        ticket = SupportTicket.objects.get(ticket_id=ok.data['data']['ticket_id'])
        self.assertEqual(ticket.attachments.count(), 2)
        url = self.customer.get('/help_center/tickets/get/', {'ticket_id': ticket.ticket_id}).data['data']['attachments'][0]['url']
        self.assertTrue(url.startswith('/help_center/tickets/attachment/?attachment_id='))
        self.assertEqual(self._create(files=[SimpleUploadedFile('x.html', b'<script>', content_type='text/html')]).status_code, 400)
        self.assertEqual(self._create(files=[SimpleUploadedFile('x.png', b'nope', content_type='image/png')]).status_code, 400)
        self.assertEqual(self._create(files=[self._png(f'{i}.png') for i in range(6)]).status_code, 400)
        self.assertEqual(SupportTicket.objects.count(), 1)                    # failed attempts leave nothing behind

    def test_attachment_download_owner_and_admin_only(self):
        ticket_id = self._create(files=[self._png()]).data['data']['ticket_id']
        attachment = SupportTicketAttachment.objects.get(ticket_id=ticket_id)
        params = {'attachment_id': attachment.attachment_id}
        resp = self.customer.get('/help_center/tickets/attachment/', params)
        self.assertEqual((resp.status_code, resp['Content-Type']), (200, 'image/png'))
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(resp.streaming_content), make_image_bytes('PNG'))
        self.assertEqual(self.admin.get('/help_center/tickets/attachment/', params).status_code, 200)
        self.assertEqual(self.artist.get('/help_center/tickets/attachment/', params).status_code, 400)
        self.assertEqual(APIClient().get('/help_center/tickets/attachment/', params).status_code, 401)

    def test_validation_and_open_ticket_limit(self):
        self.assertEqual(self._create(issue_type='nonsense').status_code, 400)
        self.assertEqual(self._create(subject='').status_code, 400)
        self.assertEqual(self._create(description='x' * 2001).status_code, 400)
        self.assertEqual(APIClient().post(self.url, {}, format='multipart').status_code, 401)
        for i in range(10):
            self.assertEqual(self._create(subject=f'T{i}').status_code, 201)
        self.assertEqual(self._create(subject='one too many').status_code, 400)

    def test_user_can_close_own_ticket_and_closing_frees_the_limit(self):
        ticket_id = self._create().data['data']['ticket_id']
        stranger, _ = make_customer(phone_number='+919000007103')
        self.assertEqual(stranger.put('/help_center/tickets/close/', {'ticket_id': ticket_id}, format='json').status_code, 400)
        self.assertEqual(self.customer.put('/help_center/tickets/close/', {'ticket_id': ticket_id}, format='json').status_code, 200)
        self.assertEqual(self.customer.put('/help_center/tickets/close/', {'ticket_id': ticket_id}, format='json').status_code, 400)
        self.assertEqual(SupportTicket.objects.get(ticket_id=ticket_id).status, 'closed')

    def test_admin_sees_all_updates_status_and_notifies_the_user(self):
        t1 = self._create().data['data']['ticket_id']
        t2 = self._create(client=self.artist, issue_type='account', subject='Locked out').data['data']['ticket_id']
        rows = self.admin.get('/help_center/admin/tickets/get_all/').data['data']['data']
        self.assertEqual([r['ticketId'] for r in rows], [t1, t2])
        self.assertEqual({r['userRole'] for r in rows}, {'customer', 'artist'})
        resp = self.admin.put('/help_center/admin/tickets/update_status/', {
            'ticket_id': t1, 'status': 'resolved', 'resolution_note': 'Refund issued'}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = self.customer.get('/help_center/tickets/get/', {'ticket_id': t1}).data['data']
        self.assertEqual((data['status'], data['resolutionNote']), ('resolved', 'Refund issued'))
        self.assertTrue(Notification.objects.filter(user_id=self.customer_user.user_id, type='support_ticket_update').exists())
        only_open = self.admin.get('/help_center/admin/tickets/get_all/', {'filter_key': 'status', 'filter_value': 'open'}).data['data']['data']
        self.assertEqual([r['ticketId'] for r in only_open], [t2])
        self.assertEqual(self.admin.get('/help_center/admin/tickets/get/', {'ticket_id': t2}).data['data']['userName'], 'Test Artist')

    def test_non_admins_cannot_use_admin_ticket_endpoints_and_closed_is_final(self):
        ticket_id = self._create().data['data']['ticket_id']
        self.assertEqual(self.customer.get('/help_center/admin/tickets/get_all/').status_code, 400)
        self.assertEqual(self.customer.put('/help_center/admin/tickets/update_status/', {'ticket_id': ticket_id, 'status': 'resolved'}, format='json').status_code, 400)
        self.assertEqual(SupportTicket.objects.get(ticket_id=ticket_id).status, 'open')
        self.customer.put('/help_center/tickets/close/', {'ticket_id': ticket_id}, format='json')
        self.assertEqual(self.admin.put('/help_center/admin/tickets/update_status/', {'ticket_id': ticket_id, 'status': 'open'}, format='json').status_code, 400)
