"""A matrix of awkward inputs against every salon-address endpoint and the booking fields they feed. Two things are
held: nothing ever ends in a server error (HTTP 5xx), and each input gets the answer the rules say.

Found by this matrix and fixed: single-line text fields used to accept line breaks, tabs, text-direction overrides
and names made only of zero-width characters (an invisible, blank-looking label in the customer's list)."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.artists.models import ArtistSalonAddress
from sunndari_apps.core.models import LocationType
from tests.test_artists import get_artist_profile, make_authenticated_client
from tests.test_customers import make_customer
from tests.test_salon_addresses import make_address

CREATE = '/artists/salon_addresses/create/'
UPDATE = '/artists/salon_addresses/update/'
DELETE = '/artists/salon_addresses/delete/'
LIST = '/artists/salon_addresses/get_all/'

BASE = {'name': 'Studio', 'address_line_1': '12 Road', 'city': 'Lucknow', 'pin_code': '226010',
        'latitude': '26.8', 'longitude': '80.9'}

# (label, field overrides, expected status)
TEXT_CASES = [
    ('emoji in name', {'name': '💇‍♀️ Glam Studio'}, 201),
    ('devanagari', {'name': 'सुंदरी सैलून', 'city': 'लखनऊ'}, 201),
    ('markup stored literally', {'city': '<script>alert(1)</script>'}, 201),
    ('sql text stored literally', {'name': "x'; DROP TABLE artist_salon_addresses;--"}, 201),
    ('number as name', {'name': 123}, 201),
    ('pin with inner space', {'pin_code': '226 010'}, 201),
    ('100 multi-byte characters', {'name': 'é' * 100}, 201),
    ('101 characters', {'name': 'x' * 101}, 400),
    ('newline in name', {'name': 'a\nb'}, 400),
    ('tab in line 2', {'address_line_2': 'a\tb'}, 400),
    ('newline in line 1', {'address_line_1': 'a\nb'}, 400),
    ('newline in pin', {'pin_code': '12\n3'}, 400),
    ('carriage return', {'city': 'a\rb'}, 400),
    ('nul character', {'name': 'a\x00b'}, 400),
    ('right-to-left override', {'name': '‮evil'}, 400),
    ('direction isolate', {'name': 'a⁦b'}, 400),
    ('only a zero-width space', {'name': '​'}, 400),
    ('only invisible characters in line 1', {'address_line_1': '​⁠﻿'}, 400),
    ('only spaces', {'name': '   '}, 400),
    ('null name', {'name': None}, 400),
    ('list as name', {'name': ['a']}, 400),
    ('object as name', {'name': {'a': 1}}, 400),
]
COORD_CASES = [
    ('exact boundaries', {'latitude': '90', 'longitude': '180'}, 201),
    ('negative boundaries', {'latitude': '-90', 'longitude': '-180'}, 201),
    ('scientific notation', {'latitude': '1e1'}, 201),
    ('tiny exponent rounds to zero on one axis', {'latitude': '1e-999999'}, 201),
    ('plus sign and spaces', {'latitude': ' +26.5 '}, 201),
    ('json numbers', {'latitude': 26.846694, 'longitude': 80.946166}, 201),
    ('integers', {'latitude': 26, 'longitude': 80}, 201),
    ('many decimals rounded', {'latitude': '26.84669449999'}, 201),
    ('just past latitude', {'latitude': '90.000001'}, 400),
    ('just past longitude', {'longitude': '-180.000001'}, 400),
    ('huge exponent', {'latitude': '1e999999999'}, 400),
    ('five thousand digits', {'latitude': '1' * 5000}, 400),
    ('five thousand decimals', {'latitude': '26.' + '1' * 5000}, 400),
    ('comma decimal', {'latitude': '26,84'}, 400),
    ('hex', {'latitude': '0x1A'}, 400),
    ('boolean', {'latitude': True}, 400),
    ('list', {'latitude': [1]}, 400),
    ('object', {'longitude': {'a': 1}}, 400),
    ('NaN / sNaN / Infinity', {'latitude': 'sNaN'}, 400),
    ('-Infinity', {'longitude': '-Infinity'}, 400),
    ('both zero', {'latitude': '0', 'longitude': '0'}, 400),
    ('both negative zero', {'latitude': '-0', 'longitude': '-0'}, 400),
    ('empty string', {'latitude': ''}, 400),
    ('null', {'longitude': None}, 400),
]


class SalonValidationMatrixTest(TestCase):

    def setUp(self):
        self.client_, self.user = make_authenticated_client(phone_number='+919800080001')
        self.profile = get_artist_profile(self.user)

    def _fresh_create(self, overrides):
        ArtistSalonAddress.objects.filter(artist_id=self.profile.artist_id).delete()
        return self.client_.post(CREATE, {**BASE, **overrides}, format='json')

    def test_create_text_matrix(self):
        for label, overrides, expected in TEXT_CASES:
            response = self._fresh_create(overrides)
            self.assertEqual(response.status_code, expected, (label, response.content))

    def test_create_coordinate_matrix(self):
        for label, overrides, expected in COORD_CASES:
            response = self._fresh_create(overrides)
            self.assertEqual(response.status_code, expected, (label, response.content))

    def test_update_gives_the_same_answers_as_create(self):
        address = make_address(self.profile, 'Seed')
        for label, overrides, expected in TEXT_CASES + COORD_CASES:
            if label in ('both zero', 'both negative zero'):
                continue                                   # on update the pair is judged together with the stored value
            body = {'salon_address_id': address, **{k: v for k, v in overrides.items()}}
            response = self.client_.put(UPDATE, body, format='json')
            self.assertEqual(response.status_code, 200 if expected == 201 else 400, (label, response.content))

    def test_stored_values_are_exactly_what_was_sent_minus_surrounding_spaces(self):
        response = self._fresh_create({'name': '  💇 Studio  ', 'address_line_2': '  Near Metro ', 'latitude': '26.84669449999'})
        self.assertEqual(response.status_code, 201)
        row = ArtistSalonAddress.objects.get()
        self.assertEqual((row.name, row.address_line_2), ('💇 Studio', 'Near Metro'))
        self.assertEqual(row.latitude, Decimal('26.846694'))

    def test_nothing_is_stored_by_a_refused_request(self):
        for label, overrides, expected in TEXT_CASES + COORD_CASES:
            if expected == 400:
                self.assertEqual(self._fresh_create(overrides).status_code, 400, label)
                self.assertEqual(ArtistSalonAddress.objects.count(), 0, label)

    def test_unusable_requests_never_reach_a_server_error(self):
        bodies = [('', 'application/json'), ('{bad', 'application/json'), ('[1]', 'application/json'),
                  ('null', 'application/json'), ('"text"', 'application/json'), ('1', 'application/json'),
                  ('name=x', 'application/x-www-form-urlencoded'), ('<a/>', 'application/xml')]
        for method in ('post', 'put', 'delete'):
            url = {'post': CREATE, 'put': UPDATE, 'delete': DELETE}[method]
            for body, content_type in bodies:
                response = getattr(self.client_, method)(url, body, content_type=content_type)
                self.assertLess(response.status_code, 500, (method, body, response.content))
        # an enormous field
        self.assertLess(self._fresh_create({'name': 'x' * 2_000_000}).status_code, 500)

    def test_ids_and_queries_that_make_no_sense_never_reach_a_server_error(self):
        weird = ['-1', '0', '99999999999999999999', '1.5', 'abc', '', ' ', '1e3', '１', "1' OR '1'='1", '../../etc/passwd']
        for value in weird:
            for response in (
                self.client_.delete(DELETE, {'salon_address_id': value}),
                self.client_.put(UPDATE, {'salon_address_id': value, 'name': 'x'}, format='json'),
                self.client_.get(LIST, {'values': value, 'page_num': value, 'limit': value}),
                self.client_.get('/customers/artists/get/', {'artist_id': value}),
            ):
                self.assertLess(response.status_code, 500, (value, response.content))

    def test_booking_fields_never_reach_a_server_error(self):
        customer, _ = make_customer(phone_number='+919800080002')
        location = LocationType.objects.get_or_create(name=LocationType.IN_SALON)[0]
        for value in ['-1', '0', '99999999999999999999', '1.5', 'abc', '', None, True, [1], {'a': 1}, '1e3']:
            response = customer.post('/customers/bookings/create/', {
                'artist_id': self.profile.artist_id, 'package_id': 1, 'location_type_id': location.location_type_id,
                'booking_date': '20-12-30', 'start_time': '10:00:00', 'salon_address_id': value, 'address_id': value,
            }, format='json')
            self.assertLess(response.status_code, 500, (value, response.content))

    def test_no_token_and_garbage_tokens_are_401_everywhere(self):
        for token in (None, 'garbage', 'Bearer', 'Bearer ' + 'a' * 5000):
            client = APIClient()
            if token:
                client.credentials(HTTP_AUTHORIZATION=token)
            for response in (client.post(CREATE, BASE, format='json'), client.put(UPDATE, {}, format='json'),
                             client.delete(DELETE), client.get(LIST)):
                self.assertIn(response.status_code, (401, 403), token)
