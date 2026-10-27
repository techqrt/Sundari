"""Step 4 of the artist service announcement: GET /core/service-sub-category/recently_activated/.

It answers one question for an artist - which services did an admin announce in the last 15 days that I have not added
yet? - from the server's clock and database only. The popup, its display frequency and what the artist has already
seen live in the app. Customers and admins get the standard refusal."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.artists.models import ArtistServiceOffering, PricingPackage
from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory

from tests.test_customers import make_artist, make_customer, make_package
from tests.test_help_center import make_admin

URL = '/core/service-sub-category/recently_activated/'
REFUSED = 'Not allowed to access this resource'


class Base(TestCase):

    def setUp(self):
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919600000002')
        self.makeup = ServiceCategory.objects.create(name='Makeup')
        self.now = timezone.now()

    def service(self, name, days_ago=0, category=None, active=True, announced=True, message=None):
        """A service announced `days_ago` days ago, set directly so no test depends on how long it took to run."""
        service = ServiceSubCategory.objects.create(category=category or self.makeup, name=name, description=f'About {name}')
        ServiceSubCategory.objects.filter(pk=service.pk).update(
            is_active=active,
            artists_announced_at=(self.now - timedelta(days=days_ago)) if announced else None,
            artists_announcement_message=(message or f'Add {name}!') if announced else None)
        return ServiceSubCategory.objects.get(pk=service.pk)

    def names(self, client=None):
        resp = (client or self.artist_client).get(URL)
        self.assertEqual(resp.status_code, 200, resp.data)
        return [row['name'] for row in resp.data['data']]


class ContentTest(Base):

    def test_an_announced_service_is_listed_with_what_the_popup_needs(self):
        service = self.service('Diwali Special', days_ago=2, message='Diwali is coming up! Add a Diwali Special service.')
        resp = self.artist_client.get(URL)
        self.assertTrue(resp.data['status'])
        item = resp.data['data'][0]
        self.assertEqual(item['subCategoryId'], service.sub_category_id)
        self.assertEqual((item['name'], item['description']), ('Diwali Special', 'About Diwali Special'))
        self.assertEqual(item['category'], {'categoryId': self.makeup.category_id, 'name': 'Makeup'})
        self.assertEqual(item['message'], 'Diwali is coming up! Add a Diwali Special service.')
        self.assertEqual(item['announcedAt'], service.artists_announced_at.isoformat())
        self.assertEqual(set(item), {'subCategoryId', 'name', 'description', 'category', 'message', 'announcedAt'})

    def test_newest_announcement_first(self):
        self.service('Older', days_ago=5)
        self.service('Newer', days_ago=1)
        self.service('Middle', days_ago=3)
        self.assertEqual(self.names(), ['Newer', 'Middle', 'Older'])

    def test_the_window_edges_are_exact(self):
        # checked on the model query with an explicit clock so the edges are exact
        inside = self.service('Just inside', days_ago=15)
        ServiceSubCategory.objects.filter(pk=inside.pk).update(artists_announced_at=self.now - timedelta(days=15) + timedelta(seconds=1))
        exact = self.service('Exactly 15 days', days_ago=15)
        outside = self.service('Just outside', days_ago=15)
        ServiceSubCategory.objects.filter(pk=outside.pk).update(artists_announced_at=self.now - timedelta(days=15, seconds=1))
        future = self.service('Future', days_ago=0)
        ServiceSubCategory.objects.filter(pk=future.pk).update(artists_announced_at=self.now + timedelta(hours=1))
        rows = ServiceSubCategory.get_announced_for_artist(self.profile.artist_id, days=15, now=self.now)
        self.assertEqual([r['name'] for r in rows], ['Just inside'])

    def test_a_service_nobody_announced_is_not_listed_even_if_new_and_live(self):
        self.service('Silent', announced=False)
        ServiceSubCategory.objects.create(category=self.makeup, name='Fresh')
        self.assertEqual(self.names(), [])

    def test_announcing_again_brings_it_back_with_the_new_time_and_wording(self):
        service = self.service('Diwali Special', days_ago=3)
        stamp = ServiceSubCategory.announce_to_artists(service.pk, 'Last call!')
        item = self.artist_client.get(URL).data['data'][0]
        self.assertEqual((item['message'], item['announcedAt']), ('Last call!', stamp.isoformat()))


class ExclusionTest(Base):

    def test_a_service_the_artist_has_added_is_not_shown_to_them_but_still_to_others(self):
        service = self.service('Diwali Special')
        other_client, _, _ = make_artist(phone_number='+919600000009')
        self.artist_client.post('/artists/services/add/', {'sub_category_id': service.pk}, format='json')
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(other_client), ['Diwali Special'])

    def test_an_active_package_counts_as_added_even_without_an_offering(self):
        service = self.service('Diwali Special')
        make_package(self.profile, sub_category=service, price=1500, name='Diwali Package')
        self.assertEqual(self.names(), [])

    def test_inactive_offerings_and_packages_do_not_count_as_added(self):
        service = self.service('Diwali Special')
        offering_id = ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=service.pk)
        ArtistServiceOffering.objects.filter(pk=offering_id).update(is_active=False)
        package = make_package(self.profile, sub_category=service, price=1500, name='Diwali Package')
        PricingPackage.objects.filter(pk=package.pk).update(is_active=False)
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_someone_elses_offering_does_not_hide_it(self):
        service = self.service('Diwali Special')
        _, _, other = make_artist(phone_number='+919600000009')
        ArtistServiceOffering.add(artist_id=other.artist_id, sub_category_id=service.pk)
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_a_switched_off_service_or_category_is_not_listed_and_returns_when_back_on(self):
        service = self.service('Diwali Special')
        for field, model, pk in (('is_active', ServiceSubCategory, service.pk), ('is_active', ServiceCategory, self.makeup.pk)):
            model.objects.filter(pk=pk).update(**{field: False})
            self.assertEqual(self.names(), [])
            model.objects.filter(pk=pk).update(**{field: True})
            self.assertEqual(self.names(), ['Diwali Special'])

    def test_switching_a_service_off_and_on_does_not_re_announce_it(self):
        service = self.service('Diwali Special', days_ago=20)
        service.is_active = False
        service.save()
        service.is_active = True
        service.save()
        self.assertEqual(self.names(), [])                          # still outside the window: activation never announces


class AccessTest(Base):

    def test_anonymous_callers_are_refused(self):
        self.assertEqual(APIClient().get(URL).status_code, 401)

    def test_customers_and_admins_get_the_standard_refusal(self):
        self.service('Diwali Special')
        customer_client, _ = make_customer(phone_number='+919600000001')
        admin_client, _ = make_admin(phone_number='+919600000003')
        for client in (customer_client, admin_client):
            resp = client.get(URL)
            self.assertEqual(resp.status_code, 400)
            self.assertFalse(resp.data['status'])
            self.assertIn(REFUSED, resp.data['message'])

    def test_an_artist_not_approved_yet_gets_an_empty_list_not_an_error(self):
        self.service('Diwali Special')
        pending_client, _, _ = make_artist(phone_number='+919600000008', approved=False)
        self.assertEqual(self.names(pending_client), [])

    def test_it_is_read_only(self):
        for method in ('post', 'put', 'delete'):
            self.assertEqual(getattr(self.artist_client, method)(URL, {}, format='json').status_code, 405)

    def test_the_window_and_clock_cannot_be_changed_by_the_client(self):
        self.service('Old', days_ago=20)
        for params in ({'days': 400}, {'recent_service_days': 400}, {'now': '2000-01-01'}, {'limit': 1, 'page_num': 9}):
            resp = self.artist_client.get(URL, params)
            self.assertEqual(resp.status_code, 200, params)
            self.assertEqual(resp.data['data'], [], params)

    def test_asking_again_never_removes_it_and_reading_the_notification_changes_nothing(self):
        self.service('Diwali Special', days_ago=1)
        self.artist_client.put('/notifications/mark_all_read/', {}, format='json')
        for _ in range(2):
            self.assertEqual(self.names(), ['Diwali Special'])

    def test_the_customer_service_list_does_not_expose_announcement_data(self):
        service = self.service('Diwali Special', days_ago=1)
        make_package(self.profile, sub_category=service, price=1500, name='Diwali Package')      # so customers can see it at all
        customer_client, _ = make_customer(phone_number='+919600000001')
        row = customer_client.get('/core/service-sub-category/get_all/').data['data']['data'][0]
        for key in ('activatedAt', 'activated_at', 'announcedAt', 'artistsAnnouncedAt', 'message'):
            self.assertNotIn(key, row)
