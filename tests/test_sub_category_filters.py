from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.core.models.service_category import ServiceCategory
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory


class ServiceSubCategoryFilterTest(TestCase):
    url = '/core/service-sub-category/get_all/'

    def setUp(self):
        user = User.objects.create(phone_number='+919000000077', role='customer', name='c')
        token = generate_jwt_token(user)
        user.access_token = token
        user.save()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.makeup = ServiceCategory.objects.create(name='Makeup')
        self.hair = ServiceCategory.objects.create(name='Hair Styling')
        ServiceSubCategory.objects.create(category=self.makeup, name='Bridal')
        ServiceSubCategory.objects.create(category=self.makeup, name='Party')
        ServiceSubCategory.objects.create(category=self.hair, name='Cut')

    def names(self, query):
        resp = self.client.get(f'{self.url}?{query}')
        self.assertEqual(resp.status_code, 200, resp.content)
        return [row['name'] for row in resp.json()['data']['data']]

    def test_no_filter_returns_everything(self):
        self.assertEqual(sorted(self.names('')), ['Bridal', 'Cut', 'Party'])

    def test_filter_by_category_id(self):
        q = f'filter_key=categoryId&filter_value={self.makeup.category_id}'
        self.assertEqual(sorted(self.names(q)), ['Bridal', 'Party'])

    def test_snake_case_alias_filters_the_same_way(self):
        q = f'filter_key=category_id&filter_value={self.hair.category_id}'
        self.assertEqual(self.names(q), ['Cut'])

    def test_filter_by_parent_service_name(self):
        self.assertEqual(sorted(self.names('filter_key=categoryName&filter_value=Makeup')), ['Bridal', 'Party'])

    def test_parent_service_name_is_a_partial_case_insensitive_match(self):
        self.assertEqual(self.names('filter_key=categoryName&filter_value=hair'), ['Cut'])

    def test_unknown_filter_key_is_rejected_not_ignored(self):
        resp = self.client.get(f'{self.url}?filter_key=nonsense&filter_value=1')
        self.assertEqual(resp.status_code, 400)

    def test_rows_carry_the_parent_service_name(self):
        rows = self.client.get(f'{self.url}?filter_key=name&filter_value=Cut').json()['data']['data']
        self.assertEqual(rows[0]['categoryName'], 'Hair Styling')

    def test_sort_by_parent_service_name(self):
        self.assertEqual(self.names('sort_by=categoryName&sort_order=asc')[0], 'Cut')
        self.assertEqual(self.names('sort_by=categoryName&sort_order=desc')[-1], 'Cut')

    def test_values_can_narrow_columns_with_a_filter(self):
        q = f'filter_key=categoryId&filter_value={self.makeup.category_id}&values=name,categoryName'
        resp = self.client.get(f'{self.url}?{q}')
        self.assertEqual(resp.status_code, 200, resp.content)
        row = resp.json()['data']['data'][0]
        self.assertEqual(set(row), {'name', 'categoryName'})
