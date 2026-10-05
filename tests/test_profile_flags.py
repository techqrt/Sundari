from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.artists.models import ArtistProfile, Portfolio, PricingPackage
from sunndari_apps.core.models import ApprovalStatus
from sunndari_apps.customers.models import Booking

from tests.test_artists import (
    make_authenticated_client, get_artist_profile, make_sub_category, make_category, make_image_bytes,
)
from tests.test_customers import (
    make_customer, make_artist, make_package, make_location_type, make_location_preference, make_schedule,
    seed_booking_statuses, next_weekday,
)


def approve(user):
    approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
    ArtistProfile.objects.filter(user_id=user.user_id).update(approval_status=approved)


class AcceptingBookingsSwitchTest(TestCase):
    url = '/artists/profile/accepting_bookings/'

    def setUp(self):
        seed_booking_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000005000')
        self.package = make_package(self.profile, price=1500)
        self.location = make_location_type('Studio')
        make_location_preference(self.profile, self.location)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        self.customer, self.customer_user = make_customer(phone_number='+919000005001')

    def _book(self, start='10:00:00'):
        return self.customer.post('/customers/bookings/create/', {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': start,
        }, format='json')

    def _found_in_search(self):
        rows = self.customer.get('/customers/artists/search/').data['data']['data']
        return any(row['artistId'] == self.profile.artist_id for row in rows)

    def test_default_is_on_and_visible(self):
        self.assertTrue(self.artist_client.get('/artists/profile/get/').data['data']['isAcceptingBookings'])
        self.assertTrue(self._found_in_search())

    def test_switching_off_hides_from_search_and_blocks_new_bookings_only(self):
        self.assertEqual(self._book().status_code, 201)                  # existing booking made while on
        resp = self.artist_client.put(self.url, {'is_accepting_bookings': False}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['data']['isAcceptingBookings'])
        self.assertFalse(self._found_in_search())
        self.assertEqual(self._book(start='13:00:00').status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)                      # the earlier booking is untouched
        self.assertEqual(Booking.objects.get().status.name, 'pending')
        self.assertFalse(self.artist_client.get('/artists/profile/get/').data['data']['isAcceptingBookings'])

    def test_switch_persists_and_can_be_turned_back_on(self):
        self.artist_client.put(self.url, {'is_accepting_bookings': False}, format='json')
        self.assertFalse(ArtistProfile.objects.get(artist_id=self.profile.artist_id).is_accepting_bookings)
        self.artist_client.put(self.url, {'is_accepting_bookings': True}, format='json')
        self.assertTrue(self._found_in_search())
        self.assertEqual(self._book().status_code, 201)

    def test_customers_see_the_flag_and_cannot_flip_it(self):
        self.artist_client.put(self.url, {'is_accepting_bookings': False}, format='json')
        detail = self.customer.get('/customers/artists/get/', {'artist_id': self.profile.artist_id}).data['data']
        self.assertFalse(detail['profile']['isAcceptingBookings'])
        self.assertEqual(self.customer.put(self.url, {'is_accepting_bookings': True}, format='json').status_code, 400)
        self.assertEqual(APIClient().put(self.url, {'is_accepting_bookings': True}, format='json').status_code, 401)
        self.assertEqual(self.artist_client.put(self.url, {}, format='json').status_code, 400)
        self.assertFalse(ArtistProfile.objects.get(artist_id=self.profile.artist_id).is_accepting_bookings)


class AgreementVersionTest(TestCase):
    def test_acceptance_records_date_and_current_version(self):
        client, user = make_authenticated_client(phone_number='+919000005010')
        with patch('sunndari.config.Configurations.agreement_version', '2.3'):
            self.assertEqual(client.put('/artists/profile/agreement/accept/', {}, format='json').status_code, 200)
        profile = get_artist_profile(user)
        self.assertIsNotNone(profile.terms_accepted_at)
        self.assertEqual(profile.agreement_version, '2.3')
        data = client.get('/artists/profile/get/').data['data']
        self.assertEqual(data['agreementVersion'], '2.3')
        self.assertIsNotNone(data['termsAcceptedAt'])

    def test_reaccepting_a_newer_version_updates_it(self):
        client, user = make_authenticated_client(phone_number='+919000005011')
        client.put('/artists/profile/agreement/accept/', {}, format='json')
        with patch('sunndari.config.Configurations.agreement_version', '9.9'):
            client.put('/artists/profile/agreement/accept/', {}, format='json')
        self.assertEqual(get_artist_profile(user).agreement_version, '9.9')

    def test_version_is_private_to_the_artist(self):
        client, user = make_authenticated_client(phone_number='+919000005012')
        client.put('/artists/profile/agreement/accept/', {}, format='json')
        approve(user)
        viewer, _ = make_authenticated_client(phone_number='+919000005013', role='customer')
        data = viewer.get('/artists/profile/get/', {'artist_id': get_artist_profile(user).artist_id}).data['data']
        self.assertNotIn('agreementVersion', data)
        self.assertNotIn('termsAcceptedAt', data)


class PublicProfileLinkTest(TestCase):
    share_url = '/artists/profile/share_link/'
    public_url = '/public/artists/get/'

    def _approved_artist(self, phone, name='Test Artist'):
        client, user = make_authenticated_client(phone_number=phone)
        client.put('/artists/profile/update/', {'display_name': 'Glam Studio', 'date_of_birth': '1990-01-01',
                                                'bio': 'Bridal specialist', 'city': 'Lucknow'}, format='json')
        sub = make_sub_category(category=make_category(name=f'Cat{phone}'), name=f'Sub{phone}')
        client.post('/artists/services/add/', {'sub_category_id': sub.sub_category_id}, format='json')
        client.put('/artists/profile/specialities/set/', {'sub_category_ids': [sub.sub_category_id]}, format='json')
        client.post('/artists/packages/create/', {'sub_category_id': sub.sub_category_id, 'name': 'Bridal',
                                                  'price': '3000', 'duration_minutes': 90}, format='json')
        for sample in (False, True):
            client.post('/artists/portfolio/create/', {
                'media_type': 'image', 'sub_category_id': sub.sub_category_id, 'is_work_sample': 'true' if sample else 'false',
                'file': SimpleUploadedFile('p.png', make_image_bytes('PNG'), content_type='image/png')}, format='multipart')
        approve(user)
        return client, user

    def test_link_is_created_once_and_stays_stable(self):
        client, user = self._approved_artist('+919000005020')
        first = client.get(self.share_url).data['data']
        second = client.get(self.share_url).data['data']
        self.assertEqual(first['slug'], second['slug'])
        self.assertTrue(first['slug'].startswith('glam-studio-'))
        self.assertTrue(first['url'].endswith(f"/public/artists/get/?slug={first['slug']}"))
        self.assertEqual(get_artist_profile(user).public_slug, first['slug'])

    def test_each_artist_gets_a_distinct_link_and_only_the_owner_asks_for_it(self):
        a, _ = self._approved_artist('+919000005021')
        b, _ = self._approved_artist('+919000005022')
        self.assertNotEqual(a.get(self.share_url).data['data']['slug'], b.get(self.share_url).data['data']['slug'])
        customer, _ = make_authenticated_client(phone_number='+919000005023', role='customer')
        self.assertEqual(customer.get(self.share_url).status_code, 400)
        self.assertEqual(APIClient().get(self.share_url).status_code, 401)

    def test_public_page_works_without_login_and_exposes_only_public_fields(self):
        client, user = self._approved_artist('+919000005024')
        slug = client.get(self.share_url).data['data']['slug']
        resp = APIClient().get(self.public_url, {'slug': slug})
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertEqual((data['displayName'], data['city'], data['bio']), ('Glam Studio', 'Lucknow', 'Bridal specialist'))
        self.assertEqual(len(data['packages']), 1)
        self.assertEqual(data['packages'][0]['name'], 'Bridal')
        self.assertEqual(len(data['portfolio']), 1)                       # the work sample stays hidden
        self.assertEqual(len(data['specialities']), 1)
        flat = str(data)
        for secret in ('userId', 'commissionRate', 'dateOfBirth', '1990', 'rejectionReason', 'approvalStatus',
                       'termsAcceptedAt', 'phone', 'email', 'publicSlug', 'artistId'):
            self.assertNotIn(secret, flat)

    def test_stray_or_expired_authorization_header_does_not_break_the_public_page(self):
        client, _ = self._approved_artist('+919000005025')
        slug = client.get(self.share_url).data['data']['slug']
        resp = APIClient().get(self.public_url, {'slug': slug}, HTTP_AUTHORIZATION='Bearer not-a-real-token')
        self.assertEqual(resp.status_code, 200)

    def test_unknown_slug_unapproved_artist_and_missing_slug_are_refused(self):
        client, user = self._approved_artist('+919000005026')
        slug = client.get(self.share_url).data['data']['slug']
        self.assertEqual(APIClient().get(self.public_url, {'slug': 'does-not-exist'}).status_code, 400)
        self.assertEqual(APIClient().get(self.public_url).status_code, 400)
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        ArtistProfile.objects.filter(user_id=user.user_id).update(approval_status=pending)
        self.assertEqual(APIClient().get(self.public_url, {'slug': slug}).status_code, 400)

    def test_hidden_packages_are_not_public(self):
        client, user = self._approved_artist('+919000005027')
        PricingPackage.objects.filter(artist=get_artist_profile(user)).update(is_active=False)
        slug = client.get(self.share_url).data['data']['slug']
        self.assertEqual(APIClient().get(self.public_url, {'slug': slug}).data['data']['packages'], [])


class ProfileViewCounterTest(TestCase):
    def test_public_page_and_customer_detail_views_are_counted_and_only_owner_sees_the_count(self):
        client, user = make_authenticated_client(phone_number='+919000005030')
        sub = make_sub_category(category=make_category(name='VC'), name='VS')
        client.post('/artists/packages/create/', {'sub_category_id': sub.sub_category_id, 'name': 'P',
                                                  'price': '1000', 'duration_minutes': 60}, format='json')
        approve(user)
        profile = get_artist_profile(user)
        self.assertEqual(client.get('/artists/profile/get/').data['data']['profileViewCount'], 0)
        customer, _ = make_authenticated_client(phone_number='+919000005031', role='customer')
        customer.get('/customers/artists/get/', {'artist_id': profile.artist_id})
        customer.get('/customers/artists/get/', {'artist_id': profile.artist_id})
        slug = client.get('/artists/profile/share_link/').data['data']['slug']
        APIClient().get('/public/artists/get/', {'slug': slug})
        self.assertEqual(client.get('/artists/profile/get/').data['data']['profileViewCount'], 3)
        public = customer.get('/artists/profile/get/', {'artist_id': profile.artist_id}).data['data']
        self.assertNotIn('profileViewCount', public)

    def test_failed_views_are_not_counted(self):
        client, user = make_authenticated_client(phone_number='+919000005032')
        customer, _ = make_authenticated_client(phone_number='+919000005033', role='customer')
        customer.get('/customers/artists/get/', {'artist_id': get_artist_profile(user).artist_id})   # not approved
        self.assertEqual(get_artist_profile(user).profile_view_count, 0)


class PortfolioReorderTest(TestCase):
    url = '/artists/portfolio/reorder/'

    def setUp(self):
        self.client_a, self.user_a = make_authenticated_client(phone_number='+919000005040')
        self.sub = make_sub_category(category=make_category(name='PR'), name='PRS')
        self.ids = [self._add(self.client_a) for _ in range(3)]

    def _add(self, client):
        resp = client.post('/artists/portfolio/create/', {
            'media_type': 'image', 'sub_category_id': self.sub.sub_category_id,
            'file': SimpleUploadedFile('p.png', make_image_bytes('PNG'), content_type='image/png')}, format='multipart')
        return resp.data['data']['portfolio_id']

    def _order(self, client=None):
        rows = (client or self.client_a).get('/artists/portfolio/get_all/').data['data']['data']
        return [row['portfolioId'] for row in rows]

    def test_new_items_go_to_the_end_by_default(self):
        self.assertEqual(self._order(), self.ids)

    def test_reorder_changes_listing_and_persists(self):
        new_order = [self.ids[2], self.ids[0], self.ids[1]]
        self.assertEqual(self.client_a.put(self.url, {'portfolio_ids': new_order}, format='json').status_code, 200)
        self.assertEqual(self._order(), new_order)
        later = self._add(self.client_a)
        self.assertEqual(self._order(), new_order + [later])

    def test_partial_list_puts_listed_first_and_keeps_the_rest_in_order(self):
        self.client_a.put(self.url, {'portfolio_ids': [self.ids[2]]}, format='json')
        self.assertEqual(self._order(), [self.ids[2], self.ids[0], self.ids[1]])

    def test_customers_see_the_artists_order(self):
        approve(self.user_a)
        self.client_a.put(self.url, {'portfolio_ids': [self.ids[1], self.ids[2], self.ids[0]]}, format='json')
        customer, _ = make_authenticated_client(phone_number='+919000005041', role='customer')
        rows = customer.get('/customers/artists/get/', {'artist_id': get_artist_profile(self.user_a).artist_id}).data['data']['portfolio']
        self.assertEqual([row['portfolioId'] for row in rows], [self.ids[1], self.ids[2], self.ids[0]])

    def test_cannot_reorder_someone_elses_items_or_send_duplicates(self):
        client_b, _ = make_authenticated_client(phone_number='+919000005042')
        foreign = self._add(client_b)
        self.assertEqual(self.client_a.put(self.url, {'portfolio_ids': [self.ids[0], foreign]}, format='json').status_code, 400)
        self.assertEqual(self.client_a.put(self.url, {'portfolio_ids': [self.ids[0], self.ids[0]]}, format='json').status_code, 400)
        self.assertEqual(self.client_a.put(self.url, {'portfolio_ids': []}, format='json').status_code, 400)
        self.assertEqual(self.client_a.put(self.url, {'portfolio_ids': [999999]}, format='json').status_code, 400)
        self.assertEqual(client_b.put(self.url, {'portfolio_ids': [self.ids[0]]}, format='json').status_code, 400)
        self.assertEqual(self._order(), self.ids)
        self.assertEqual(APIClient().put(self.url, {'portfolio_ids': [1]}, format='json').status_code, 401)
