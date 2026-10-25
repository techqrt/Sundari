"""Task 4 of the service-activation feature: GET /core/service-sub-category/recently_activated/.

It answers one question - which services went live in the last 15 days and still are? - from the server's clock
and database only. The popup, its display frequency and what the user has already seen live in the app."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory

from tests.test_customers import make_artist, make_customer
from tests.test_help_center import make_admin

URL = '/core/service-sub-category/recently_activated/'


class RecentlyActivatedBase(TestCase):

    def setUp(self):
        self.client_customer, self.customer = make_customer(phone_number='+919600000001')
        self.makeup = ServiceCategory.objects.create(name='Makeup')
        self.now = timezone.now()

    def service(self, name, days_ago=None, category=None, active=True, activated_at='default'):
        """A service whose activation time is set directly (the model rule would stamp 'now' on creation)."""
        service = ServiceSubCategory.objects.create(category=category or self.makeup, name=name, description=f'About {name}')
        stamp = self.now - timedelta(days=days_ago) if days_ago is not None else None
        if activated_at != 'default':
            stamp = activated_at
        ServiceSubCategory.objects.filter(pk=service.pk).update(is_active=active, activated_at=stamp)
        return ServiceSubCategory.objects.get(pk=service.pk)

    def names(self, client=None):
        resp = (client or self.client_customer).get(URL)
        self.assertEqual(resp.status_code, 200, resp.data)
        return [row['name'] for row in resp.data['data']]


class WindowTest(RecentlyActivatedBase):

    def test_a_service_activated_inside_15_days_is_listed_with_what_the_popup_needs(self):
        service = self.service('Bridal Makeup', days_ago=2)
        resp = self.client_customer.get(URL)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        item = resp.data['data'][0]
        self.assertEqual(item['subCategoryId'], service.sub_category_id)
        self.assertEqual((item['name'], item['description']), ('Bridal Makeup', 'About Bridal Makeup'))
        self.assertEqual(item['category'], {'categoryId': self.makeup.category_id, 'name': 'Makeup'})
        self.assertEqual(item['activatedAt'], service.activated_at.isoformat())
        self.assertEqual(set(item), {'subCategoryId', 'name', 'description', 'category', 'activatedAt'})

    def test_the_window_edges_are_exact(self):
        # Checked on the model query with an explicit clock so no test depends on how long it took to run.
        a = self.service('Just inside', activated_at=self.now - timedelta(days=15) + timedelta(seconds=1))
        b = self.service('Exactly 15 days', activated_at=self.now - timedelta(days=15))
        c = self.service('Just outside', activated_at=self.now - timedelta(days=15, seconds=1))
        d = self.service('Right now', activated_at=self.now)
        listed = [row['name'] for row in ServiceSubCategory.get_recently_activated(days=15, now=self.now)]
        self.assertEqual(sorted(listed), ['Just inside', 'Right now'])

    def test_older_than_15_days_is_not_listed(self):
        self.service('Old', days_ago=16)
        self.service('Ancient', days_ago=200)
        self.assertEqual(self.names(), [])

    def test_a_service_dated_in_the_future_is_not_listed(self):
        self.service('Scheduled', activated_at=self.now + timedelta(days=1))
        self.assertEqual(self.names(), [])

    def test_a_service_activated_before_tracking_began_is_never_new(self):
        self.service('Legacy', activated_at=None)
        self.assertEqual(self.names(), [])

    def test_newest_first(self):
        self.service('Oldest', days_ago=10)
        self.service('Newest', days_ago=1)
        self.service('Middle', days_ago=5)
        self.assertEqual(self.names(), ['Newest', 'Middle', 'Oldest'])

    def test_nothing_new_is_an_empty_list_not_an_error(self):
        resp = self.client_customer.get(URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data'], [])


class ExclusionTest(RecentlyActivatedBase):

    def test_a_service_switched_off_since_is_not_listed(self):
        service = self.service('Bridal Makeup', days_ago=1)
        service.is_active = False
        service.save()
        self.assertEqual(self.names(), [])

    def test_a_service_under_a_switched_off_category_is_not_listed_and_returns_with_it(self):
        self.service('Bridal Makeup', days_ago=1)
        self.makeup.is_active = False
        self.makeup.save()
        self.assertEqual(self.names(), [])
        self.makeup.is_active = True
        self.makeup.save()
        self.assertEqual(self.names(), ['Bridal Makeup'])

    def test_switching_one_service_off_leaves_its_new_siblings_listed(self):
        off = self.service('Party Makeup', days_ago=1)
        self.service('Bridal Makeup', days_ago=2)
        off.is_active = False
        off.save()
        self.assertEqual(self.names(), ['Bridal Makeup'])

    def test_switching_a_service_off_and_on_again_starts_a_new_window(self):
        service = self.service('Bridal Makeup', days_ago=30)
        self.assertEqual(self.names(), [])
        service.is_active = False
        service.save()
        service.is_active = True
        service.save()
        self.assertEqual(self.names(), ['Bridal Makeup'])

    def test_a_brand_new_service_created_active_is_listed(self):
        ServiceSubCategory.objects.create(category=self.makeup, name='Fresh')
        self.assertEqual(self.names(), ['Fresh'])

    def test_a_service_created_inactive_is_not_listed_until_it_is_switched_on(self):
        service = ServiceSubCategory.objects.create(category=self.makeup, name='Later', is_active=False)
        self.assertEqual(self.names(), [])
        service.is_active = True
        service.save()
        self.assertEqual(self.names(), ['Later'])


class AccessTest(RecentlyActivatedBase):

    def test_anonymous_callers_are_refused(self):
        self.assertEqual(APIClient().get(URL).status_code, 401)

    def test_customers_artists_and_admins_all_get_the_same_list(self):
        self.service('Bridal Makeup', days_ago=1)
        artist_client, _, _ = make_artist(phone_number='+919600000002')
        admin_client, _ = make_admin(phone_number='+919600000003')
        for client in (self.client_customer, artist_client, admin_client):
            self.assertEqual(self.names(client), ['Bridal Makeup'])

    def test_it_is_read_only(self):
        for method in ('post', 'put', 'delete'):
            self.assertEqual(getattr(self.client_customer, method)(URL, {}, format='json').status_code, 405)

    def test_the_window_and_clock_cannot_be_changed_by_the_client(self):
        self.service('Old', days_ago=20)
        for params in ({'days': 400}, {'recent_service_days': 400}, {'now': '2000-01-01'}, {'limit': 1, 'page_num': 9}):
            resp = self.client_customer.get(URL, params)
            self.assertEqual(resp.status_code, 200, params)
            self.assertEqual(resp.data['data'], [], params)

    def test_it_does_not_depend_on_who_asks_or_what_they_have_seen_or_been_notified_about(self):
        self.service('Bridal Makeup', days_ago=1)
        other_client, _ = make_customer(phone_number='+919600000004')
        self.assertEqual(self.names(self.client_customer), self.names(other_client))
        for _ in range(2):                                     # asking again never removes it: remembering is the app's job
            self.assertEqual(self.names(), ['Bridal Makeup'])

    def test_the_existing_service_list_does_not_expose_the_activation_time(self):
        self.service('Bridal Makeup', days_ago=1)
        row = self.client_customer.get('/core/service-sub-category/get_all/').data['data']['data'][0]
        self.assertNotIn('activatedAt', row)
        self.assertNotIn('activated_at', row)
