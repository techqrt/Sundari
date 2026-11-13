"""An artist's salon addresses (a customer picks one when booking In-Salon).

Feature 1: POST /artists/salon_addresses/create/. Every call works on the caller's own profile; there is no artist
id in the request, so nobody can add to another artist's list."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistSalonAddress
from sunndari_apps.core.models.approval_status import ApprovalStatus
from tests.test_artists import get_artist_profile, make_authenticated_client
from tests.test_customers import make_customer

CREATE = '/artists/salon_addresses/create/'


def payload(**overrides):
    body = {
        'name': 'Gomti Nagar Studio', 'address_line_1': '12 Vibhuti Khand', 'address_line_2': 'Near Metro Pillar 120',
        'city': 'Lucknow', 'pin_code': '226010', 'latitude': '26.846694', 'longitude': '80.946166',
    }
    body.update(overrides)
    return {key: value for key, value in body.items() if value is not None or key in overrides}


class CreateSalonAddressTest(TestCase):

    def setUp(self):
        self.client_, self.user = make_authenticated_client(phone_number='+919800030001')
        self.profile = get_artist_profile(self.user)

    def _post(self, client=None, **overrides):
        return (client or self.client_).post(CREATE, payload(**overrides), format='json')

    def _rows(self, profile=None):
        return ArtistSalonAddress.objects.filter(artist_id=(profile or self.profile).artist_id)

    # --- success
    def test_an_artist_can_add_a_salon_address(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data['status'])
        self.assertEqual(resp.data['message'], 'Salon address added successfully')
        row = self._rows().get()
        self.assertEqual(resp.data['data'], {'salon_address_id': row.salon_address_id})
        self.assertEqual(
            (row.name, row.address_line_1, row.address_line_2, row.city, row.pin_code, row.is_active),
            ('Gomti Nagar Studio', '12 Vibhuti Khand', 'Near Metro Pillar 120', 'Lucknow', '226010', True))
        self.assertEqual((row.latitude, row.longitude), (Decimal('26.846694'), Decimal('80.946166')))

    def test_an_artist_can_add_several_addresses(self):
        ids = []
        for n, city in enumerate(('Lucknow', 'Kanpur', 'Varanasi')):
            resp = self._post(name=f'Studio {n}', city=city)
            self.assertEqual(resp.status_code, 201, resp.data)
            ids.append(resp.data['data']['salon_address_id'])
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(self._rows().count(), 3)

    def test_the_second_line_is_optional(self):
        for n, extra in enumerate(({'address_line_2': None}, {'address_line_2': ''}, {'address_line_2': '   '})):
            self.assertEqual(self._post(name=f'S{n}', **extra).status_code, 201)
        body = payload(name='No line two')
        del body['address_line_2']
        self.assertEqual(self.client_.post(CREATE, body, format='json').status_code, 201)
        self.assertEqual(self._rows().filter(address_line_2__isnull=True).count(), 4)

    def test_surrounding_spaces_are_trimmed(self):
        self._post(name='  Glam Studio  ', address_line_1='  1 MG Road ', city=' Lucknow ', pin_code=' 226001 ')
        row = self._rows().get()
        self.assertEqual((row.name, row.address_line_1, row.city, row.pin_code), ('Glam Studio', '1 MG Road', 'Lucknow', '226001'))

    def test_an_artist_still_being_reviewed_can_add_addresses_like_any_other(self):
        self.assertEqual(self.profile.approval_status.name, 'pending')
        self.assertEqual(self._post().status_code, 201)
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(
            approval_status=ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})[0])
        self.assertEqual(self._post(name='Second').status_code, 201)

    # --- ownership
    def test_the_address_always_goes_to_the_caller_whatever_the_request_says(self):
        other_client, other_user = make_authenticated_client(phone_number='+919800030002')
        other = get_artist_profile(other_user)
        resp = self._post(artist_id=other.artist_id, user_id=other_user.user_id, is_active=False, salon_address_id=999)
        self.assertEqual(resp.status_code, 201, resp.data)
        row = self._rows().get()
        self.assertEqual((row.artist_id, row.is_active), (self.profile.artist_id, True))
        self.assertNotEqual(row.salon_address_id, 999)
        self.assertEqual(self._rows(other).count(), 0)

    def test_two_artists_can_use_the_same_name(self):
        other_client, other_user = make_authenticated_client(phone_number='+919800030003')
        self.assertEqual(self._post().status_code, 201)
        self.assertEqual(self._post(client=other_client).status_code, 201)
        self.assertEqual(ArtistSalonAddress.objects.count(), 2)

    # --- who may call it
    def test_a_request_without_a_token_is_refused(self):
        self.assertEqual(APIClient().post(CREATE, payload(), format='json').status_code, 401)
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_a_customer_cannot_add_a_salon_address(self):
        customer, _ = make_customer(phone_number='+919800030004')
        resp = customer.post(CREATE, payload(), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(Constants.artist_not_found, resp.data['message'])
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_an_admin_account_has_no_artist_profile_to_add_to(self):
        admin, _ = make_authenticated_client(phone_number='+919800030005', role='admin')
        self.assertEqual(admin.post(CREATE, payload(), format='json').status_code, 400)
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    # --- validation
    def test_every_required_field_is_required(self):
        for field in ('name', 'address_line_1', 'city', 'pin_code', 'latitude', 'longitude'):
            body = payload()
            del body[field]
            resp = self.client_.post(CREATE, body, format='json')
            self.assertEqual(resp.status_code, 400, field)
            self.assertFalse(resp.data['status'])
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_blank_or_empty_values_are_refused(self):
        for field in ('name', 'address_line_1', 'city', 'pin_code'):
            for value in ('', '   ', None):
                self.assertEqual(self._post(**{field: value}).status_code, 400, (field, value))
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_text_longer_than_the_limits_is_refused(self):
        for field, limit in (('name', 100), ('address_line_1', 255), ('address_line_2', 255), ('city', 100), ('pin_code', 10)):
            self.assertEqual(self._post(**{field: 'x' * limit}).status_code, 201, f'{field} at its limit')
            ArtistSalonAddress.objects.all().delete()
            self.assertEqual(self._post(**{field: 'x' * (limit + 1)}).status_code, 400, f'{field} over its limit')
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_coordinates_outside_the_earth_are_refused(self):
        for lat, lng in (('90.000001', '80'), ('-90.000001', '80'), ('26', '180.000001'), ('26', '-180.000001'),
                         ('91', '80'), ('26', '181'), ('1000', '1000')):
            self.assertEqual(self._post(latitude=lat, longitude=lng).status_code, 400, (lat, lng))
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_rounding_never_lets_a_value_past_the_limits(self):
        # outside the range as sent: refused, even by a hair
        self.assertEqual(self._post(latitude='90.0000004', longitude='80').status_code, 400)
        self.assertEqual(self._post(latitude='26', longitude='-180.0000004').status_code, 400)
        # inside the range as sent: rounded to six places, up to the limit itself but never beyond it
        self.assertEqual(self._post(name='Rounds up', latitude='89.9999996', longitude='179.9999996').status_code, 201)
        self.assertEqual(self._post(name='Rounds down', latitude='26.8466944', longitude='80.9461664').status_code, 201)
        up, down = self._rows().get(name='Rounds up'), self._rows().get(name='Rounds down')
        self.assertEqual((up.latitude, up.longitude), (Decimal('90.000000'), Decimal('180.000000')))
        self.assertEqual((down.latitude, down.longitude), (Decimal('26.846694'), Decimal('80.946166')))

    def test_the_extreme_valid_coordinates_are_accepted(self):
        for n, (lat, lng) in enumerate((('90', '180'), ('-90', '-180'), ('90', '-180'), ('-90', '180'), ('0', '80'), ('26', '0'))):
            self.assertEqual(self._post(name=f'Edge {n}', latitude=lat, longitude=lng).status_code, 201, (lat, lng))

    def test_coordinates_must_be_numbers_and_both_must_be_sent(self):
        for lat, lng in (('abc', '80'), ('26', 'abc'), ('', '80'), ('26', ''), (None, '80'), ('26', None), ([], '80'), ('NaN', '80'), ('Infinity', '80')):
            self.assertEqual(self._post(latitude=lat, longitude=lng).status_code, 400, (lat, lng))
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_an_unset_map_position_of_zero_zero_is_refused(self):
        for lat, lng in (('0', '0'), (0, 0), ('0.0', '0.000000')):
            resp = self._post(latitude=lat, longitude=lng)
            self.assertEqual(resp.status_code, 400, (lat, lng))
            self.assertIn(Constants.salon_coordinates_unset, str(resp.data))

    def test_extra_decimals_from_a_map_are_rounded_not_refused(self):
        resp = self._post(latitude='26.84669450', longitude=80.9461664999)
        self.assertEqual(resp.status_code, 201, resp.data)
        row = self._rows().get()
        self.assertEqual((row.latitude, row.longitude), (Decimal('26.846695'), Decimal('80.946166')))

    def test_coordinates_may_be_sent_as_json_numbers(self):
        self.assertEqual(self._post(latitude=26.846694, longitude=80.946166).status_code, 201)
        self.assertEqual(self._rows().get().latitude, Decimal('26.846694'))

    def test_a_request_with_no_body_or_a_wrong_shape_is_refused_cleanly(self):
        self.assertEqual(self.client_.post(CREATE, {}, format='json').status_code, 400)
        self.assertEqual(self.client_.post(CREATE, [], format='json').status_code, 400)
        self.assertEqual(self.client_.post(CREATE, 'text', format='json').status_code, 400)
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)

    def test_text_is_stored_as_given_so_markup_is_never_interpreted(self):
        self.assertEqual(self._post(name='<b>Studio</b> & "Co"', address_line_1="'; DROP TABLE users;--").status_code, 201)
        row = self._rows().get()
        self.assertEqual((row.name, row.address_line_1), ('<b>Studio</b> & "Co"', "'; DROP TABLE users;--"))

    # --- names and limits
    def test_a_name_can_be_used_once_among_active_addresses_ignoring_case_and_spaces(self):
        self.assertEqual(self._post(name='Glam Studio').status_code, 201)
        for name in ('Glam Studio', 'glam studio', 'GLAM STUDIO', '  Glam Studio  '):
            resp = self._post(name=name)
            self.assertEqual(resp.status_code, 400, name)
            self.assertIn(Constants.salon_address_exists, resp.data['message'])
        self.assertEqual(self._rows().count(), 1)

    def test_a_switched_off_address_frees_its_name_and_its_place(self):
        self._post(name='Old Studio')
        self._rows().update(is_active=False)
        self.assertEqual(self._post(name='Old Studio').status_code, 201)
        self.assertEqual(self._rows().count(), 2)
        self.assertEqual(self._rows().filter(is_active=True).count(), 1)

    def test_an_artist_can_have_ten_active_addresses_and_not_eleven(self):
        for n in range(10):
            self.assertEqual(self._post(name=f'Studio {n}').status_code, 201, n)
        resp = self._post(name='Studio 10')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('at most 10', resp.data['message'])
        self.assertEqual(self._rows().count(), 10)
        # removing (switching off) one makes room
        self._rows().filter(name='Studio 0').update(is_active=False)
        self.assertEqual(self._post(name='Studio 10').status_code, 201)
        self.assertEqual(self._rows().filter(is_active=True).count(), 10)

    def test_the_limit_is_per_artist(self):
        for n in range(10):
            self._post(name=f'Studio {n}')
        other_client, _ = make_authenticated_client(phone_number='+919800030006')
        self.assertEqual(self._post(client=other_client, name='Studio 0').status_code, 201)

    # --- what the database enforces on its own
    def test_the_database_refuses_an_impossible_position_even_without_the_serializer(self):
        for lat, lng in ((91, 80), (-91, 80), (26, 181), (26, -181)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                ArtistSalonAddress.objects.create(
                    artist=self.profile, name='Bad', address_line_1='x', city='x', pin_code='1', latitude=lat, longitude=lng)

    def test_the_database_refuses_two_active_addresses_with_one_name(self):
        ArtistSalonAddress.objects.create(artist=self.profile, name='Studio', address_line_1='x', city='x', pin_code='1', latitude=1, longitude=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArtistSalonAddress.objects.create(artist=self.profile, name='STUDIO', address_line_1='y', city='y', pin_code='2', latitude=2, longitude=2)

    def test_deleting_an_artist_profile_takes_its_salon_addresses_with_it(self):
        self._post()
        self.assertEqual(ArtistSalonAddress.objects.count(), 1)
        self.user.delete()
        self.assertEqual(ArtistSalonAddress.objects.count(), 0)


GET_ALL = '/artists/salon_addresses/get_all/'


def make_address(profile, name='Gomti Nagar Studio', **overrides):
    fields = dict(
        artist_id=profile.artist_id, name=name, address_line_1='12 Vibhuti Khand', city='Lucknow',
        pin_code='226010', latitude=Decimal('26.846694'), longitude=Decimal('80.946166'),
    )
    fields.update(overrides)
    return ArtistSalonAddress().create(**fields)


class ListSalonAddressesTest(TestCase):
    """Feature 2: GET /artists/salon_addresses/get_all/ shows the caller's own active addresses only."""

    def setUp(self):
        self.client_, self.user = make_authenticated_client(phone_number='+919800030011')
        self.profile = get_artist_profile(self.user)

    def _rows(self, client=None):
        response = (client or self.client_).get(GET_ALL)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def test_empty_when_none_added(self):
        self.assertEqual(self._rows(), [])

    def test_returns_fields_with_numeric_coordinates(self):
        address_id = make_address(self.profile, address_line_2='Near Metro')
        row = self._rows()[0]
        self.assertEqual(row['salon_address_id'], address_id)
        self.assertEqual(row['name'], 'Gomti Nagar Studio')
        self.assertEqual(row['address_line_2'], 'Near Metro')
        self.assertEqual(row['city'], 'Lucknow')
        self.assertEqual(row['pin_code'], '226010')
        self.assertEqual(row['latitude'], 26.846694)
        self.assertEqual(row['longitude'], 80.946166)
        self.assertIn('created_at', row)

    def test_oldest_first(self):
        first = make_address(self.profile, 'A')
        second = make_address(self.profile, 'B')
        third = make_address(self.profile, 'C')
        self.assertEqual([r['salon_address_id'] for r in self._rows()], [first, second, third])

    def test_inactive_hidden(self):
        keep = make_address(self.profile, 'Keep')
        gone = make_address(self.profile, 'Gone')
        ArtistSalonAddress.objects.filter(pk=gone).update(is_active=False)
        self.assertEqual([r['salon_address_id'] for r in self._rows()], [keep])

    def test_never_shows_another_artists_addresses(self):
        other_client, other_user = make_authenticated_client(phone_number='+919800030012')
        other_profile = get_artist_profile(other_user)
        make_address(other_profile, 'Theirs')
        mine = make_address(self.profile, 'Mine')
        self.assertEqual([r['salon_address_id'] for r in self._rows()], [mine])
        # An artist_id in the query changes nothing.
        response = self.client_.get(GET_ALL, {'artist_id': other_profile.artist_id})
        self.assertEqual([r['salon_address_id'] for r in response.json()['data']], [mine])

    def test_created_through_the_api_appears(self):
        self.client_.post(CREATE, payload(), format='json')
        self.assertEqual(len(self._rows()), 1)

    def test_unauthenticated_refused(self):
        self.assertEqual(APIClient().get(GET_ALL).status_code, 401)

    def test_customer_without_artist_profile_refused(self):
        customer_client, _ = make_customer(phone_number='+919800030013')
        response = customer_client.get(GET_ALL)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.artist_not_found, response.json()['message'])

    def test_post_not_allowed(self):
        self.assertEqual(self.client_.post(GET_ALL, {}, format='json').status_code, 405)


UPDATE = '/artists/salon_addresses/update/'


class UpdateSalonAddressTest(TestCase):
    """Feature 3: PUT /artists/salon_addresses/update/ edits the caller's own active address, partially."""

    def setUp(self):
        self.client_, self.user = make_authenticated_client(phone_number='+919800030021')
        self.profile = get_artist_profile(self.user)
        self.address_id = make_address(self.profile, address_line_2='Near Metro')

    def _put(self, body, client=None):
        return (client or self.client_).put(UPDATE, body, format='json')

    def _fresh(self, address_id=None):
        return ArtistSalonAddress.objects.get(pk=address_id or self.address_id)

    def test_edit_one_field_keeps_the_rest(self):
        response = self._put({'salon_address_id': self.address_id, 'city': 'Kanpur'})
        self.assertEqual(response.status_code, 200, response.content)
        row = self._fresh()
        self.assertEqual(row.city, 'Kanpur')
        self.assertEqual(row.name, 'Gomti Nagar Studio')
        self.assertEqual(row.address_line_2, 'Near Metro')
        self.assertEqual(row.latitude, Decimal('26.846694'))
        self.assertTrue(row.is_active)

    def test_edit_every_field(self):
        body = {'salon_address_id': self.address_id, 'name': ' New Name ', 'address_line_1': ' 5 Hazratganj ',
                'address_line_2': 'Opp. Park', 'city': 'Lucknow', 'pin_code': '226001',
                'latitude': '26.85', 'longitude': '80.94'}
        self.assertEqual(self._put(body).status_code, 200)
        row = self._fresh()
        self.assertEqual((row.name, row.address_line_1, row.address_line_2, row.pin_code),
                         ('New Name', '5 Hazratganj', 'Opp. Park', '226001'))
        self.assertEqual((row.latitude, row.longitude), (Decimal('26.85'), Decimal('80.94')))

    def test_clear_address_line_2(self):
        for cleared in (None, '', '   '):
            ArtistSalonAddress.objects.filter(pk=self.address_id).update(address_line_2='Near Metro')
            self.assertEqual(self._put({'salon_address_id': self.address_id, 'address_line_2': cleared}).status_code, 200)
            self.assertIsNone(self._fresh().address_line_2)

    def test_omitted_line_2_is_kept(self):
        self._put({'salon_address_id': self.address_id, 'name': 'Other'})
        self.assertEqual(self._fresh().address_line_2, 'Near Metro')

    def test_coordinates_rounded_to_six_places(self):
        self._put({'salon_address_id': self.address_id, 'latitude': '26.8466945', 'longitude': '80.9461664'})
        row = self._fresh()
        self.assertEqual((row.latitude, row.longitude), (Decimal('26.846695'), Decimal('80.946166')))

    def test_updated_at_moves_and_list_shows_new_value(self):
        before = self._fresh().updated_at
        self._put({'salon_address_id': self.address_id, 'name': 'Renamed'})
        self.assertGreater(self._fresh().updated_at, before)
        self.assertEqual(self.client_.get(GET_ALL).json()['data'][0]['name'], 'Renamed')

    def test_keeping_own_name_or_changing_its_case_is_allowed(self):
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'name': 'Gomti Nagar Studio'}).status_code, 200)
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'name': 'GOMTI NAGAR STUDIO'}).status_code, 200)
        self.assertEqual(self._fresh().name, 'GOMTI NAGAR STUDIO')

    def test_name_taken_by_another_of_my_addresses_refused(self):
        make_address(self.profile, 'Hazratganj Studio')
        response = self._put({'salon_address_id': self.address_id, 'name': ' hazratganj studio '})
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_exists, response.json()['message'])
        self.assertEqual(self._fresh().name, 'Gomti Nagar Studio')

    def test_name_used_by_a_switched_off_address_is_free(self):
        old = make_address(self.profile, 'Old Studio')
        ArtistSalonAddress.objects.filter(pk=old).update(is_active=False)
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'name': 'Old Studio'}).status_code, 200)

    def test_same_name_as_another_artists_address_is_fine(self):
        _, other_user = make_authenticated_client(phone_number='+919800030022')
        make_address(get_artist_profile(other_user), 'Shared Name')
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'name': 'Shared Name'}).status_code, 200)

    def test_cannot_edit_another_artists_address(self):
        other_client, other_user = make_authenticated_client(phone_number='+919800030023')
        theirs = make_address(get_artist_profile(other_user), 'Theirs')
        response = self._put({'salon_address_id': theirs, 'name': 'Hijacked'})
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_not_found, response.json()['message'])
        self.assertEqual(self._fresh(theirs).name, 'Theirs')

    def test_unknown_and_switched_off_address_not_found(self):
        self.assertEqual(self._put({'salon_address_id': 999999, 'name': 'X'}).status_code, 400)
        ArtistSalonAddress.objects.filter(pk=self.address_id).update(is_active=False)
        response = self._put({'salon_address_id': self.address_id, 'name': 'X'})
        self.assertIn(Constants.salon_address_not_found, response.json()['message'])
        self.assertEqual(self._fresh().name, 'Gomti Nagar Studio')

    def test_ownership_and_active_flag_cannot_be_changed(self):
        _, other_user = make_authenticated_client(phone_number='+919800030024')
        other = get_artist_profile(other_user)
        self._put({'salon_address_id': self.address_id, 'name': 'Same', 'artist_id': other.artist_id, 'is_active': False})
        row = self._fresh()
        self.assertEqual(row.artist_id, self.profile.artist_id)
        self.assertTrue(row.is_active)

    def test_nothing_to_change_refused(self):
        response = self._put({'salon_address_id': self.address_id})
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_nothing_to_update, str(response.json()))

    def test_salon_address_id_required_and_numeric(self):
        self.assertEqual(self._put({'name': 'X'}).status_code, 400)
        self.assertEqual(self._put({'salon_address_id': 'abc', 'name': 'X'}).status_code, 400)

    def test_invalid_values_refused_and_nothing_saved(self):
        bad = [{'name': ''}, {'name': 'x' * 101}, {'address_line_1': '  '}, {'city': ''}, {'pin_code': '1' * 11},
               {'latitude': '90.5'}, {'latitude': '-91'}, {'longitude': '180.1'}, {'longitude': 'abc'},
               {'latitude': 'NaN'}, {'longitude': 'Infinity'}]
        for change in bad:
            response = self._put({'salon_address_id': self.address_id, **change})
            self.assertEqual(response.status_code, 400, change)
        row = self._fresh()
        self.assertEqual((row.name, row.city, row.latitude), ('Gomti Nagar Studio', 'Lucknow', Decimal('26.846694')))

    def test_zero_zero_refused_even_when_only_one_axis_changes(self):
        ArtistSalonAddress.objects.filter(pk=self.address_id).update(latitude=Decimal('0'))
        response = self._put({'salon_address_id': self.address_id, 'longitude': '0'})
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_coordinates_unset, response.json()['message'])
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'longitude': '10'}).status_code, 200)

    def test_zero_on_one_axis_alone_is_fine(self):
        self.assertEqual(self._put({'salon_address_id': self.address_id, 'latitude': '0', 'longitude': '80.9'}).status_code, 200)

    def test_unauthenticated_refused(self):
        self.assertEqual(APIClient().put(UPDATE, {'salon_address_id': 1, 'name': 'X'}, format='json').status_code, 401)

    def test_customer_refused(self):
        customer_client, _ = make_customer(phone_number='+919800030025')
        response = self._put({'salon_address_id': self.address_id, 'name': 'X'}, client=customer_client)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.artist_not_found, response.json()['message'])

    def test_post_not_allowed(self):
        self.assertEqual(self.client_.post(UPDATE, {}, format='json').status_code, 405)


DELETE = '/artists/salon_addresses/delete/'


class DeleteSalonAddressTest(TestCase):
    """Feature 4: DELETE /artists/salon_addresses/delete/ switches the address off; the row is kept for history."""

    def setUp(self):
        self.client_, self.user = make_authenticated_client(phone_number='+919800030031')
        self.profile = get_artist_profile(self.user)
        self.address_id = make_address(self.profile)

    def _delete(self, address_id=None, client=None):
        return (client or self.client_).delete(DELETE, {'salon_address_id': address_id or self.address_id})

    def test_delete_switches_off_and_keeps_the_row(self):
        response = self._delete()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['message'], 'Salon address deleted successfully')
        row = ArtistSalonAddress.objects.get(pk=self.address_id)
        self.assertFalse(row.is_active)
        self.assertEqual(row.name, 'Gomti Nagar Studio')

    def test_disappears_from_list_and_other_addresses_stay(self):
        keep = make_address(self.profile, 'Keep')
        self._delete()
        self.assertEqual([r['salon_address_id'] for r in self.client_.get(GET_ALL).json()['data']], [keep])

    def test_frees_the_name(self):
        self._delete()
        self.assertEqual(self.client_.post(CREATE, payload(), format='json').status_code, 201)

    def test_frees_a_slot_at_the_limit(self):
        for i in range(ArtistSalonAddress.MAX_ACTIVE_PER_ARTIST - 1):
            make_address(self.profile, f'Extra {i}')
        self.assertEqual(self.client_.post(CREATE, payload(name='Over'), format='json').status_code, 400)
        self._delete()
        self.assertEqual(self.client_.post(CREATE, payload(name='Fits'), format='json').status_code, 201)

    def test_cannot_be_edited_after_delete(self):
        self._delete()
        response = self.client_.put(UPDATE, {'salon_address_id': self.address_id, 'name': 'Back'}, format='json')
        self.assertIn(Constants.salon_address_not_found, response.json()['message'])

    def test_second_delete_not_found(self):
        self._delete()
        response = self._delete()
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_not_found, response.json()['message'])

    def test_cannot_delete_another_artists_address(self):
        _, other_user = make_authenticated_client(phone_number='+919800030032')
        theirs = make_address(get_artist_profile(other_user), 'Theirs')
        response = self._delete(theirs)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_not_found, response.json()['message'])
        self.assertTrue(ArtistSalonAddress.objects.get(pk=theirs).is_active)

    def test_unknown_id_not_found(self):
        self.assertEqual(self._delete(999999).status_code, 400)

    def test_id_required_and_numeric(self):
        self.assertEqual(self.client_.delete(DELETE).status_code, 400)
        self.assertEqual(self.client_.delete(DELETE, {'salon_address_id': 'abc'}).status_code, 400)

    def test_unauthenticated_refused(self):
        self.assertEqual(APIClient().delete(DELETE, {'salon_address_id': 1}).status_code, 401)

    def test_customer_refused(self):
        customer_client, _ = make_customer(phone_number='+919800030033')
        response = self._delete(client=customer_client)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.artist_not_found, response.json()['message'])
        self.assertTrue(ArtistSalonAddress.objects.get(pk=self.address_id).is_active)

    def test_get_not_allowed(self):
        self.assertEqual(self.client_.get(DELETE).status_code, 405)

    def test_id_in_the_query_string_works(self):
        self.assertEqual(self.client_.delete(f'{DELETE}?salon_address_id={self.address_id}').status_code, 200)
        self.assertFalse(ArtistSalonAddress.objects.get(pk=self.address_id).is_active)
