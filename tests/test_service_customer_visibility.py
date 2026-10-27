"""Step 5 of the artist service announcement: customers see a service only once it can actually be booked.

A service is bookable for customers when it is live AND at least one active package under it belongs to an approved
artist who is accepting bookings. Artists still see every live service (so they can add one nobody offers yet) and admins
see everything."""
from django.test import TestCase

from sunndari_apps.artists.models import ArtistServiceOffering, PricingPackage
from sunndari_apps.core.models import ApprovalStatus, ServiceCategory, ServiceSubCategory

from tests.test_customers import make_artist, make_customer, make_package
from tests.test_help_center import make_admin

SUBS = '/core/service-sub-category/get_all/'


class VisibilityTest(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Seasonal')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Diwali Special')
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919400000001')
        self.customer_client, _ = make_customer(phone_number='+919400000002')
        self.admin_client, _ = make_admin(phone_number='+919400000003')

    def names(self, client=None, **params):
        resp = (client or self.customer_client).get(SUBS, params)
        self.assertEqual(resp.status_code, 200, resp.data)
        return [row['name'] for row in resp.data['data']['data']]

    def package(self, profile=None, **kw):
        return make_package(profile or self.profile, sub_category=kw.pop('sub_category', self.service), price=1500, name=kw.pop('name', 'Pkg'), **kw)

    def set_status(self, profile, name):
        status, _ = ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name})
        profile.approval_status = status
        profile.save()

    # ── the rule ─────────────────────────────────────────────────────────────

    def test_a_live_service_nobody_offers_yet_is_hidden_from_customers_but_not_from_artists_or_admins(self):
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(self.artist_client), ['Diwali Special'])
        self.assertEqual(self.names(self.admin_client), ['Diwali Special'])

    def test_it_appears_for_customers_as_soon_as_an_artist_adds_a_package(self):
        self.artist_client.post('/artists/services/add/', {'sub_category_id': self.service.pk}, format='json')
        self.assertEqual(self.names(), [])                                    # adding the service alone is not enough
        self.package()
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_an_offering_without_a_package_does_not_show_it(self):
        ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=self.service.pk)
        self.assertEqual(self.names(), [])

    def test_it_disappears_again_when_the_last_package_is_switched_off(self):
        package = self.package()
        self.assertEqual(self.names(), ['Diwali Special'])
        PricingPackage.objects.filter(pk=package.pk).update(is_active=False)
        self.assertEqual(self.names(), [])
        PricingPackage.objects.filter(pk=package.pk).update(is_active=True)
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_one_inactive_package_does_not_hide_it_while_another_is_active(self):
        off = self.package(name='Off')
        PricingPackage.objects.filter(pk=off.pk).update(is_active=False)
        self.package(name='On')
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_an_artist_who_is_not_approved_does_not_make_it_visible(self):
        self.package()
        for state in ('pending', 'rejected', 'suspended'):
            self.set_status(self.profile, state)
            self.assertEqual(self.names(), [], state)
        self.set_status(self.profile, 'approved')
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_an_artist_not_accepting_bookings_does_not_make_it_visible(self):
        self.package()
        type(self.profile).objects.filter(pk=self.profile.pk).update(is_accepting_bookings=False)
        self.assertEqual(self.names(), [])
        type(self.profile).objects.filter(pk=self.profile.pk).update(is_accepting_bookings=True)
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_another_artists_bookable_package_is_enough(self):
        self.package()
        self.set_status(self.profile, 'suspended')
        _, _, other = make_artist(phone_number='+919400000009')
        self.package(other)
        self.assertEqual(self.names(), ['Diwali Special'])

    def test_many_packages_and_artists_list_the_service_once(self):
        self.package(name='A')
        self.package(name='B')
        _, _, other = make_artist(phone_number='+919400000009')
        self.package(other, name='C')
        resp = self.customer_client.get(SUBS)
        self.assertEqual(self.names(), ['Diwali Special'])
        self.assertEqual(resp.data['data']['data'][0]['name'], 'Diwali Special')

    def test_a_package_under_another_service_does_not_expose_this_one(self):
        other = ServiceSubCategory.objects.create(category=self.category, name='Holi Special')
        self.package(sub_category=other)
        self.assertEqual(self.names(), ['Holi Special'])

    def test_a_switched_off_service_or_category_stays_hidden_even_with_a_package(self):
        self.package()
        ServiceSubCategory.objects.filter(pk=self.service.pk).update(is_active=False)
        self.assertEqual(self.names(), [])
        ServiceSubCategory.objects.filter(pk=self.service.pk).update(is_active=True)
        ServiceCategory.objects.filter(pk=self.category.pk).update(is_active=False)
        self.assertEqual(self.names(), [])
        self.assertEqual(self.names(self.artist_client), [])                  # not live for artists either
        self.assertEqual(self.names(self.admin_client), ['Diwali Special'])

    # ── the rest of the list keeps working under the rule ────────────────────

    def test_filters_search_sort_and_paging_apply_to_what_the_customer_can_see(self):
        names = ['Alpha', 'Bravo', 'Charlie', 'Delta']
        for name in names:
            sub = ServiceSubCategory.objects.create(category=self.category, name=name)
            if name != 'Charlie':                                              # Charlie has no package
                self.package(sub_category=sub, name=f'{name} pkg')
        self.assertEqual(self.names(), ['Alpha', 'Bravo', 'Delta'])
        self.assertEqual(self.names(search_key='a'), ['Alpha', 'Bravo', 'Delta'])
        self.assertEqual(self.names(search_key='Charlie'), [])
        self.assertEqual(self.names(sort_by='name', sort_order='desc'), ['Delta', 'Bravo', 'Alpha'])
        page = self.customer_client.get(SUBS, {'limit': 2, 'page_num': 2}).data['data']
        self.assertEqual([r['name'] for r in page['data']], ['Delta'])
        self.assertEqual(self.names(filter_key='categoryId', filter_value=str(self.category.pk)), ['Alpha', 'Bravo', 'Delta'])

    def test_a_service_can_still_be_looked_up_by_id_so_old_references_resolve(self):
        resp = self.customer_client.get('/core/service-sub-category/get/', {'sub_category_id': self.service.pk})
        self.assertEqual(resp.status_code, 200)

    def test_the_full_artist_journey_makes_it_visible_to_customers(self):
        stamp = ServiceSubCategory.announce_to_artists(self.service.pk, 'Diwali is coming up!')
        self.assertIsNotNone(stamp)
        self.assertEqual(self.names(), [])                                    # announced, but nobody offers it yet
        self.assertEqual(len(self.artist_client.get('/core/service-sub-category/recently_activated/').data['data']), 1)
        self.assertEqual(self.artist_client.post('/artists/services/add/', {'sub_category_id': self.service.pk}, format='json').status_code, 201)
        created = self.artist_client.post('/artists/packages/create/', {
            'sub_category_id': self.service.pk, 'name': 'Diwali Glam', 'price': '2200', 'duration_minutes': 90}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.names(), ['Diwali Special'])
        self.assertEqual(self.artist_client.get('/core/service-sub-category/recently_activated/').data['data'], [])
