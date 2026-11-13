"""Feature 5: the salon address a customer picks is saved on the booking, by booking type.

Home Visit and On-Site Event need the customer's own address_id and refuse a salon_address_id. In-Salon needs one of
the booked artist's active salon addresses and ignores address_id. Nothing is ever picked for the customer. The booking
keeps a snapshot, so editing or deleting the address never rewrites it."""
from decimal import Decimal

from django.db.models import RestrictedError
from django.test import TestCase

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistSalonAddress, ArtistServiceArea
from sunndari_apps.customers.models import Booking
from sunndari_apps.core.models import LocationType
from sunndari_apps.users.models.customer_address import CustomerAddress
from tests.booking_address import address_for
from tests.booking_paid import pay_booking
from tests.test_customers import (
    make_artist, make_customer, make_sub_category, make_package, make_location_type, make_location_preference,
    make_schedule, next_weekday, seed_booking_statuses,
)
from tests.test_salon_addresses import make_address

URL = '/customers/bookings/create/'


class SalonBookingTest(TestCase):

    def setUp(self):
        self.client_, self.customer = make_customer(phone_number='+919800040001')
        _, self.artist_user, self.profile = make_artist(phone_number='+919800040002')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=60)
        self.home = make_location_type(LocationType.HOME_VISIT)
        self.salon = make_location_type(LocationType.IN_SALON)
        self.event = make_location_type(LocationType.ON_SITE_EVENT)
        for location_type in (self.home, self.salon, self.event):
            make_location_preference(self.profile, location_type)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        seed_booking_statuses()
        self.salon_id = make_address(self.profile)

    def _book(self, location_type, client=None, start='10:00:00', **extra):
        body = {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': location_type.location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': start,
        }
        body.update(extra)
        return (client or self.client_).post(URL, body, format='json')

    def _bookings(self):
        return Booking.objects.filter(customer_id=self.customer.user_id)

    def _in_salon(self, **extra):
        return self._book(self.salon, salon_address_id=self.salon_id, **extra)

    # -- In-Salon ------------------------------------------------------------------------------------------------
    def test_in_salon_saves_the_chosen_address_and_a_snapshot(self):
        response = self._in_salon()
        self.assertEqual(response.status_code, 201, response.content)
        booking = Booking.objects.get(booking_id=response.data['data']['booking_id'])
        self.assertEqual(booking.salon_address_id, self.salon_id)
        self.assertIsNone(booking.address_id)
        self.assertEqual(booking.salon_address_snapshot, {
            'salon_address_id': self.salon_id, 'name': 'Gomti Nagar Studio', 'address_line_1': '12 Vibhuti Khand',
            'address_line_2': None, 'city': 'Lucknow', 'pin_code': '226010',
            'latitude': 26.846694, 'longitude': 80.946166,
        })

    def test_in_salon_needs_no_customer_address(self):
        self.assertFalse(CustomerAddress.objects.filter(user=self.customer).exists())
        self.assertEqual(self._in_salon().status_code, 201)

    def test_in_salon_ignores_a_customer_address_sent_along(self):
        other_client, other = make_customer(phone_number='+919800040003')
        foreign = address_for(other_client)
        response = self._in_salon(**foreign)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(self._bookings().get().address_id)

    def test_in_salon_without_a_salon_is_refused_and_nothing_is_chosen_for_the_customer(self):
        # The artist has exactly one salon address: it must still not be picked automatically.
        for body in ({}, {'salon_address_id': None}, {'salon_address_id': 0}, {**address_for(self.client_)}):
            response = self._book(self.salon, **body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn(Constants.salon_address_required, response.json()['message'])
        self.assertEqual(self._bookings().count(), 0)

    def test_in_salon_with_another_artists_address_is_refused(self):
        _, _, other_profile = make_artist(phone_number='+919800040004')
        theirs = make_address(other_profile, 'Theirs')
        response = self._book(self.salon, salon_address_id=theirs)
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.salon_address_unavailable, response.json()['message'])
        self.assertEqual(self._bookings().count(), 0)

    def test_in_salon_with_a_deleted_or_unknown_address_is_refused(self):
        ArtistSalonAddress.objects.filter(pk=self.salon_id).update(is_active=False)
        for salon_id in (self.salon_id, 999999):
            response = self._book(self.salon, salon_address_id=salon_id)
            self.assertIn(Constants.salon_address_unavailable, response.json()['message'])
        self.assertEqual(self._bookings().count(), 0)

    def test_in_salon_non_numeric_salon_id_refused(self):
        self.assertEqual(self._book(self.salon, salon_address_id='abc').status_code, 400)

    def test_artist_without_in_salon_preference_still_refused(self):
        from sunndari_apps.artists.models import ArtistLocationPreference
        ArtistLocationPreference.objects.filter(
            artist_id=self.profile.artist_id, location_type_id=self.salon.location_type_id).delete()
        self.assertEqual(self._in_salon().status_code, 400)

    def test_in_salon_charges_no_travel_fee_even_with_service_areas(self):
        ArtistServiceArea.objects.create(
            artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        response = self._in_salon()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['data']['travel_fee'], '0.00')
        self.assertEqual(response.data['data']['total_amount'], '1500.00')

    # -- Home Visit / On-Site Event --------------------------------------------------------------------------------
    def test_home_visit_and_event_save_no_salon(self):
        for location_type, start in ((self.home, '10:00:00'), (self.event, '13:00:00')):
            response = self._book(location_type, start=start, **address_for(self.client_))
            self.assertEqual(response.status_code, 201, response.content)
            booking = Booking.objects.get(booking_id=response.data['data']['booking_id'])
            self.assertIsNone(booking.salon_address_id)
            self.assertIsNone(booking.salon_address_snapshot)
            self.assertIsNotNone(booking.address_id)

    def test_salon_address_refused_for_home_visit_and_event(self):
        for location_type in (self.home, self.event):
            response = self._book(location_type, salon_address_id=self.salon_id, **address_for(self.client_))
            self.assertEqual(response.status_code, 400)
            self.assertIn(Constants.salon_address_not_allowed, response.json()['message'])
        self.assertEqual(self._bookings().count(), 0)

    def test_address_still_required_for_home_visit_and_event(self):
        for location_type in (self.home, self.event):
            for body in ({}, {'address_id': None}):
                response = self._book(location_type, **body)
                self.assertEqual(response.status_code, 400)
                self.assertIn(Constants.customer_address_required, response.json()['message'])
        self.assertEqual(self._bookings().count(), 0)

    def test_someone_elses_customer_address_still_refused(self):
        other_client, _ = make_customer(phone_number='+919800040005')
        response = self._book(self.home, **address_for(other_client))
        self.assertEqual(response.status_code, 400)
        self.assertIn(Constants.data_no_match, response.json()['message'])

    # -- History ----------------------------------------------------------------------------------------------------
    def test_booking_keeps_its_snapshot_when_the_address_is_edited(self):
        booking = Booking.objects.get(booking_id=self._in_salon().data['data']['booking_id'])
        ArtistSalonAddress.objects.get(pk=self.salon_id).update_fields(name='Renamed', city='Kanpur', latitude=Decimal('1'))
        booking.refresh_from_db()
        self.assertEqual(booking.salon_address_snapshot['name'], 'Gomti Nagar Studio')
        self.assertEqual(booking.salon_address_snapshot['city'], 'Lucknow')
        self.assertEqual(booking.salon_address_snapshot['latitude'], 26.846694)

    def test_booking_survives_the_address_being_deleted(self):
        booking = Booking.objects.get(booking_id=self._in_salon().data['data']['booking_id'])
        ArtistSalonAddress.objects.get(pk=self.salon_id).deactivate()
        booking.refresh_from_db()
        self.assertEqual(booking.salon_address_id, self.salon_id)
        self.assertEqual(booking.salon_address_snapshot['name'], 'Gomti Nagar Studio')

    def test_a_used_address_cannot_be_erased_but_an_unused_one_can(self):
        self._in_salon()
        with self.assertRaises(RestrictedError):
            ArtistSalonAddress.objects.get(pk=self.salon_id).delete()
        unused = make_address(self.profile, 'Unused')
        ArtistSalonAddress.objects.get(pk=unused).delete()
        self.assertFalse(ArtistSalonAddress.objects.filter(pk=unused).exists())

    def test_removing_an_artist_after_their_bookings_still_works(self):
        # (An artist with bookings is already protected by their packages; this only shows the salon link is no
        # extra obstacle once the bookings are gone.)
        self._in_salon()
        Booking.objects.filter(artist_id=self.profile.artist_id).delete()
        self.profile.delete()
        self.assertFalse(ArtistSalonAddress.objects.filter(pk=self.salon_id).exists())

    def test_older_style_booking_without_a_salon_is_valid(self):
        from tests.test_customers import make_booking
        booking = make_booking(self.customer, self.profile, self.package, self.salon, self.date, '09:00', '10:00')
        self.assertIsNone(booking.salon_address_id)
        self.assertIsNone(booking.salon_address_snapshot)


class SalonBookingResponseTest(TestCase):
    """Feature 6: every booking response shows the salon (name, address, latitude, longitude) for an In-Salon booking
    and null for the other types, read from the snapshot saved on the booking."""

    def setUp(self):
        self.client_, self.customer = make_customer(phone_number='+919800050001')
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919800050002')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=60)
        self.home = make_location_type(LocationType.HOME_VISIT)
        self.salon = make_location_type(LocationType.IN_SALON)
        for location_type in (self.home, self.salon):
            make_location_preference(self.profile, location_type)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        seed_booking_statuses()
        self.salon_id = make_address(self.profile, address_line_2='Near Metro')
        body = {'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
                'booking_date': self.date.strftime('%d-%m-%y')}
        response = self.client_.post(URL, {**body, 'location_type_id': self.salon.location_type_id,
                                           'salon_address_id': self.salon_id, 'start_time': '10:00:00'}, format='json')
        self.salon_booking = response.data['data']['booking_id']
        response = self.client_.post(URL, {**body, 'location_type_id': self.home.location_type_id,
                                           'start_time': '13:00:00', **address_for(self.client_)}, format='json')
        self.home_booking = response.data['data']['booking_id']
        # An artist sees a booking only once it is paid.
        pay_booking(self.salon_booking)
        pay_booking(self.home_booking)

    EXPECTED = {
        'salonAddressId': None, 'name': 'Gomti Nagar Studio', 'addressLine1': '12 Vibhuti Khand',
        'addressLine2': 'Near Metro', 'city': 'Lucknow', 'pinCode': '226010',
        'latitude': 26.846694, 'longitude': 80.946166,
    }

    def _expected(self):
        return {**self.EXPECTED, 'salonAddressId': self.salon_id}

    def _customer_get(self, booking_id, **query):
        response = self.client_.get('/customers/bookings/get/', {'booking_id': booking_id, **query})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def _artist_get(self, booking_id, **query):
        response = self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id, **query})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def test_customer_get_shows_the_salon_with_coordinates(self):
        data = self._customer_get(self.salon_booking)
        self.assertEqual(data['salonAddress'], self._expected())
        self.assertIsNone(data['address'])

    def test_artist_get_shows_the_salon_with_coordinates(self):
        data = self._artist_get(self.salon_booking)
        self.assertEqual(data['salonAddress'], self._expected())

    def test_home_visit_shows_null_salon_and_its_own_address(self):
        for data in (self._customer_get(self.home_booking), self._artist_get(self.home_booking)):
            self.assertIsNone(data['salonAddress'])
            self.assertIsNotNone(data['address'])

    def test_customer_list_has_the_salon_on_the_right_booking_only(self):
        rows = {row['bookingId']: row for row in self.client_.get('/customers/bookings/get_all/').json()['data']['data']}
        self.assertEqual(rows[self.salon_booking]['salonAddress'], self._expected())
        self.assertIsNone(rows[self.home_booking]['salonAddress'])

    def test_artist_list_has_the_salon_on_the_right_booking_only(self):
        response = self.artist_client.get('/artists/bookings/get_all/')
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row['bookingId']: row for row in response.json()['data']['data']}
        self.assertEqual(rows[self.salon_booking]['salonAddress'], self._expected())
        self.assertIsNone(rows[self.home_booking]['salonAddress'])

    def test_response_keeps_the_saved_salon_after_an_edit(self):
        ArtistSalonAddress.objects.get(pk=self.salon_id).update_fields(
            name='Renamed', city='Kanpur', latitude=Decimal('1.5'), longitude=Decimal('2.5'))
        self.assertEqual(self._customer_get(self.salon_booking)['salonAddress'], self._expected())
        self.assertEqual(self._artist_get(self.salon_booking)['salonAddress'], self._expected())

    def test_response_keeps_the_saved_salon_after_a_delete(self):
        ArtistSalonAddress.objects.get(pk=self.salon_id).deactivate()
        self.assertEqual(self._customer_get(self.salon_booking)['salonAddress'], self._expected())
        self.assertEqual(self._artist_get(self.salon_booking)['salonAddress'], self._expected())

    def test_another_customer_still_cannot_see_the_booking(self):
        other_client, _ = make_customer(phone_number='+919800050003')
        response = other_client.get('/customers/bookings/get/', {'booking_id': self.salon_booking})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Gomti Nagar', response.content.decode())

    def test_older_booking_without_a_salon_shows_null(self):
        from tests.test_customers import make_booking
        booking = make_booking(self.customer, self.profile, self.package, self.salon, self.date, '16:00', '17:00')
        self.assertIsNone(self._customer_get(booking.booking_id)['salonAddress'])

    def test_firestore_copy_carries_the_salon(self):
        from unittest.mock import patch, MagicMock
        from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
        client = MagicMock()
        with patch('sunndari_apps.customers.firebase_utils.FirebaseUtils.get_client', return_value=client):
            BookingFirebaseUtils.sync_booking(self.salon_booking)
            BookingFirebaseUtils.sync_booking(self.home_booking)
        sent = [call.args[0] for call in client.collection.return_value.document.return_value.set.call_args_list]
        self.assertEqual(sent[0]['salonAddress'], self._expected())
        self.assertIsNone(sent[1]['salonAddress'])


class CustomerSalonChoiceTest(TestCase):
    """Feature 7: the customer's artist page lists the artist's active salons, and the customer books In-Salon by
    choosing one of them: the whole flow, page to booking."""

    def setUp(self):
        self.client_, self.customer = make_customer(phone_number='+919800060001')
        _, self.artist_user, self.profile = make_artist(phone_number='+919800060002')
        self.package = make_package(self.profile, sub_category=make_sub_category(), price=1500, duration=60)
        self.salon_type = make_location_type(LocationType.IN_SALON)
        make_location_preference(self.profile, self.salon_type)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        seed_booking_statuses()

    def _page(self, artist_id=None, client=None):
        response = (client or self.client_).get('/customers/artists/get/', {'artist_id': artist_id or self.profile.artist_id})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def test_page_lists_every_active_salon_with_coordinates_oldest_first(self):
        first = make_address(self.profile, 'Gomti Nagar Studio', address_line_2='Near Metro')
        second = make_address(self.profile, 'Hazratganj Studio', latitude=Decimal('26.85'), longitude=Decimal('80.94'))
        salons = self._page()['salonAddresses']
        self.assertEqual([s['salonAddressId'] for s in salons], [first, second])
        self.assertEqual(salons[0], {
            'salonAddressId': first, 'name': 'Gomti Nagar Studio', 'addressLine1': '12 Vibhuti Khand',
            'addressLine2': 'Near Metro', 'city': 'Lucknow', 'pinCode': '226010',
            'latitude': 26.846694, 'longitude': 80.946166,
        })
        self.assertEqual((salons[1]['latitude'], salons[1]['longitude']), (26.85, 80.94))

    def test_empty_list_when_the_artist_has_none(self):
        self.assertEqual(self._page()['salonAddresses'], [])

    def test_deleted_salon_is_not_offered(self):
        keep = make_address(self.profile, 'Keep')
        gone = make_address(self.profile, 'Gone')
        ArtistSalonAddress.objects.get(pk=gone).deactivate()
        self.assertEqual([s['salonAddressId'] for s in self._page()['salonAddresses']], [keep])

    def test_page_never_shows_another_artists_salons(self):
        _, _, other = make_artist(phone_number='+919800060003')
        make_address(other, 'Theirs')
        mine = make_address(self.profile, 'Mine')
        self.assertEqual([s['salonAddressId'] for s in self._page()['salonAddresses']], [mine])

    def test_hidden_artist_page_exposes_no_salons(self):
        make_address(self.profile)
        self.profile.is_accepting_bookings = False
        self.profile.save()
        response = self.client_.get('/customers/artists/get/', {'artist_id': self.profile.artist_id})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Gomti Nagar', response.content.decode())

    def test_artist_page_still_needs_a_login(self):
        from rest_framework.test import APIClient
        make_address(self.profile)
        self.assertEqual(APIClient().get('/customers/artists/get/', {'artist_id': self.profile.artist_id}).status_code, 401)

    def test_whole_flow_page_choice_booking_response(self):
        make_address(self.profile, 'Gomti Nagar Studio')
        wanted = make_address(self.profile, 'Hazratganj Studio', address_line_1='5 Hazratganj',
                              latitude=Decimal('26.85'), longitude=Decimal('80.94'))
        offered = {s['salonAddressId'] for s in self._page()['salonAddresses']}
        self.assertIn(wanted, offered)
        response = self.client_.post(URL, {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.salon_type.location_type_id, 'salon_address_id': wanted,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        booking_id = response.data['data']['booking_id']
        data = self.client_.get('/customers/bookings/get/', {'booking_id': booking_id}).json()['data']
        self.assertEqual(data['salonAddress']['name'], 'Hazratganj Studio')
        self.assertEqual((data['salonAddress']['latitude'], data['salonAddress']['longitude']), (26.85, 80.94))
        self.assertEqual(data['salonAddress']['addressLine1'], '5 Hazratganj')

    def test_the_page_shape_matches_the_booking_shape(self):
        sid = make_address(self.profile)
        listed = self._page()['salonAddresses'][0]
        response = self.client_.post(URL, {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.salon_type.location_type_id, 'salon_address_id': sid,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': '10:00:00',
        }, format='json')
        data = self.client_.get('/customers/bookings/get/', {'booking_id': response.data['data']['booking_id']}).json()['data']
        self.assertEqual(data['salonAddress'], listed)
