from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.artists.models import PackageAddOn, ArtistServiceArea, ArtistProfile
from sunndari_apps.core.models import LocationType, PaymentStatus
from sunndari_apps.customers.models import Booking, BookingAddOn, BookingReschedule
from sunndari_apps.payments.models import Payment
from sunndari_apps.users.models.customer_address import CustomerAddress

from tests.test_customers import (
    make_customer, make_artist, make_sub_category, make_package, make_location_type,
    make_location_preference, make_schedule, seed_booking_statuses, seed_payment_statuses, next_weekday,
)


def make_address_in(user, city):
    return CustomerAddress.objects.get(
        address_id=CustomerAddress().create(user_id=user.user_id, address_line_1='1 Main Rd', city=city, pin_code='226001')
    )


class AddOnCrudTest(TestCase):
    def setUp(self):
        self.client_a, self.user_a, self.profile_a = make_artist(phone_number='+919000002000')
        self.package = make_package(self.profile_a, price=2000)
        self.package2 = make_package(self.profile_a, name='Second', price=3000)

    def _create(self, client=None, **extra):
        payload = {'name': 'Hair styling', 'price': '500.00', 'duration_minutes': 30,
                   'package_ids': [self.package.package_id], **extra}
        return (client or self.client_a).post('/artists/addons/create/', payload, format='json')

    def test_create_get_and_list_with_linked_packages(self):
        resp = self._create(description='Curls or waves')
        self.assertEqual(resp.status_code, 201)
        addon_id = resp.data['data']['addon_id']
        data = self.client_a.get('/artists/addons/get/', {'addon_id': addon_id}).data['data']
        self.assertEqual((data['name'], data['price'], data['durationMinutes'], data['isActive']),
                         ('Hair styling', '500.00', 30, True))
        self.assertEqual(data['packageIds'], [self.package.package_id])
        listed = self.client_a.get('/artists/addons/get_all/').data['data']['data']
        self.assertEqual([row['addOnId'] for row in listed], [addon_id])
        self.assertEqual(listed[0]['packageIds'], [self.package.package_id])

    def test_update_replaces_packages_and_changes_only_sent_fields(self):
        addon_id = self._create().data['data']['addon_id']
        resp = self.client_a.put('/artists/addons/update/', {
            'addon_id': addon_id, 'price': '650.00', 'package_ids': [self.package2.package_id],
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        data = self.client_a.get('/artists/addons/get/', {'addon_id': addon_id}).data['data']
        self.assertEqual((data['name'], data['price']), ('Hair styling', '650.00'))
        self.assertEqual(data['packageIds'], [self.package2.package_id])
        self.client_a.put('/artists/addons/update/', {'addon_id': addon_id, 'package_ids': []}, format='json')
        self.assertEqual(self.client_a.get('/artists/addons/get/', {'addon_id': addon_id}).data['data']['packageIds'], [])

    def test_delete_removes_addon_but_not_packages(self):
        addon_id = self._create().data['data']['addon_id']
        self.assertEqual(self.client_a.delete(f'/artists/addons/delete/?addon_id={addon_id}').status_code, 200)
        self.assertFalse(PackageAddOn.objects.filter(addon_id=addon_id).exists())
        self.assertEqual(self.client_a.get('/artists/packages/get_all/').data['data']['data'].__len__(), 2)

    def test_cannot_link_another_artists_package(self):
        _, _, profile_b = make_artist(phone_number='+919000002001')
        foreign_package = make_package(profile_b)
        resp = self._create(package_ids=[foreign_package.package_id])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PackageAddOn.objects.count(), 0)
        addon_id = self._create().data['data']['addon_id']
        resp = self.client_a.put('/artists/addons/update/', {
            'addon_id': addon_id, 'package_ids': [foreign_package.package_id],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_other_artist_cannot_read_edit_or_delete(self):
        addon_id = self._create().data['data']['addon_id']
        client_b, _, _ = make_artist(phone_number='+919000002002')
        self.assertEqual(client_b.get('/artists/addons/get/', {'addon_id': addon_id}).status_code, 400)
        self.assertEqual(client_b.put('/artists/addons/update/', {'addon_id': addon_id, 'name': 'x'}, format='json').status_code, 400)
        self.assertEqual(client_b.delete(f'/artists/addons/delete/?addon_id={addon_id}').status_code, 400)
        self.assertEqual(PackageAddOn.objects.get(addon_id=addon_id).name, 'Hair styling')

    def test_validation_and_auth(self):
        self.assertEqual(self._create(price='0').status_code, 400)
        self.assertEqual(self._create(duration_minutes=-5).status_code, 400)
        self.assertEqual(self._create(name='').status_code, 400)
        customer, _ = make_customer(phone_number='+919000002003')
        self.assertEqual(self._create(client=customer).status_code, 400)
        self.assertEqual(self._create(client=APIClient()).status_code, 401)

    def test_other_users_see_only_active_addons_of_approved_artists(self):
        self._create(name='Visible')
        hidden_id = self._create(name='Hidden').data['data']['addon_id']
        self.client_a.put('/artists/addons/update/', {'addon_id': hidden_id, 'is_active': False}, format='json')
        customer, _ = make_customer(phone_number='+919000002004')
        rows = customer.get('/artists/addons/get_all/', {'artist_id': self.profile_a.artist_id}).data['data']['data']
        self.assertEqual([row['name'] for row in rows], ['Visible'])
        own = self.client_a.get('/artists/addons/get_all/').data['data']['data']
        self.assertEqual(len(own), 2)
        _, _, unapproved = make_artist(phone_number='+919000002005', approved=False)
        self.assertEqual(customer.get('/artists/addons/get_all/', {'artist_id': unapproved.artist_id}).status_code, 400)

    def test_customer_artist_detail_lists_active_addons_and_service_areas(self):
        self._create(name='Visible')
        hidden_id = self._create(name='Hidden').data['data']['addon_id']
        self.client_a.put('/artists/addons/update/', {'addon_id': hidden_id, 'is_active': False}, format='json')
        ArtistServiceArea.objects.create(artist=self.profile_a, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        ArtistServiceArea.objects.create(artist=self.profile_a, city='Agra', travel_charge_type='free', is_active=False)
        customer, _ = make_customer(phone_number='+919000002006')
        resp = customer.get('/customers/artists/get/', {'artist_id': self.profile_a.artist_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertEqual([a['name'] for a in data['addOns']], ['Visible'])
        self.assertEqual(data['addOns'][0]['packageIds'], [self.package.package_id])
        self.assertEqual([(a['city'], a['chargeAmount']) for a in data['serviceAreas']], [('Lucknow', '250.00')])


class ServiceAreaApiTest(TestCase):
    def setUp(self):
        self.client_a, self.user_a, self.profile_a = make_artist(phone_number='+919000002100')

    def _add(self, client=None, **payload):
        return (client or self.client_a).post('/artists/service_areas/add/', payload, format='json')

    def test_add_list_update_remove(self):
        resp = self._add(city='Lucknow', travel_charge_type='per_visit', charge_amount='250.00')
        self.assertEqual(resp.status_code, 201)
        area_id = resp.data['data']['area_id']
        self._add(city='Kanpur', travel_charge_type='free')
        rows = self.client_a.get('/artists/service_areas/get_all/').data['data']
        self.assertEqual([(r['city'], r['travelChargeType'], r['chargeAmount']) for r in rows],
                         [('Lucknow', 'per_visit', '250.00'), ('Kanpur', 'free', '0.00')])
        self.assertEqual(self.client_a.put('/artists/service_areas/update/', {
            'area_id': area_id, 'charge_amount': '300.00'}, format='json').status_code, 200)
        self.assertEqual(ArtistServiceArea.objects.get(area_id=area_id).charge_amount, Decimal('300.00'))
        self.assertEqual(self.client_a.delete(f'/artists/service_areas/remove/?area_id={area_id}').status_code, 200)
        self.assertEqual(len(self.client_a.get('/artists/service_areas/get_all/').data['data']), 1)

    def test_charge_rules(self):
        self.assertEqual(self._add(city='A', travel_charge_type='per_visit').status_code, 400)
        self.assertEqual(self._add(city='A', travel_charge_type='per_visit', charge_amount='0').status_code, 400)
        self.assertEqual(self._add(city='A', travel_charge_type='free', charge_amount='50').status_code, 400)
        self.assertEqual(self._add(city='A', travel_charge_type='per_visit', charge_amount='-5').status_code, 400)
        self.assertEqual(self._add(city='A', travel_charge_type='sometimes').status_code, 400)
        self.assertEqual(ArtistServiceArea.objects.count(), 0)

    def test_per_km_is_refused_until_a_distance_source_exists(self):
        resp = self._add(city='Lucknow', travel_charge_type='per_km', charge_amount='12')
        self.assertEqual(resp.status_code, 400)
        area_id = self._add(city='Lucknow', travel_charge_type='free').data['data']['area_id']
        resp = self.client_a.put('/artists/service_areas/update/', {
            'area_id': area_id, 'travel_charge_type': 'per_km', 'charge_amount': '12'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_update_keeps_type_and_amount_consistent(self):
        area_id = self._add(city='Lucknow', travel_charge_type='per_visit', charge_amount='250').data['data']['area_id']
        self.client_a.put('/artists/service_areas/update/', {'area_id': area_id, 'travel_charge_type': 'free'}, format='json')
        area = ArtistServiceArea.objects.get(area_id=area_id)
        self.assertEqual((area.travel_charge_type, area.charge_amount), ('free', Decimal('0')))
        resp = self.client_a.put('/artists/service_areas/update/', {'area_id': area_id, 'travel_charge_type': 'per_visit'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_city_unique_per_artist_case_insensitive_but_not_across_artists(self):
        self._add(city='Lucknow', travel_charge_type='free')
        self.assertEqual(self._add(city='  lucknow ', travel_charge_type='free').status_code, 400)
        client_b, _, _ = make_artist(phone_number='+919000002101')
        self.assertEqual(self._add(client=client_b, city='Lucknow', travel_charge_type='free').status_code, 201)

    def test_ownership_and_auth(self):
        area_id = self._add(city='Lucknow', travel_charge_type='free').data['data']['area_id']
        client_b, _, _ = make_artist(phone_number='+919000002102')
        self.assertEqual(client_b.put('/artists/service_areas/update/', {'area_id': area_id, 'city': 'X'}, format='json').status_code, 400)
        self.assertEqual(client_b.delete(f'/artists/service_areas/remove/?area_id={area_id}').status_code, 400)
        self.assertEqual(ArtistServiceArea.objects.get(area_id=area_id).city, 'Lucknow')
        customer, _ = make_customer(phone_number='+919000002103')
        self.assertEqual(customer.post('/artists/service_areas/add/', {'city': 'X', 'travel_charge_type': 'free'}, format='json').status_code, 400)
        self.assertEqual(APIClient().get('/artists/service_areas/get_all/').status_code, 401)

    def test_other_users_see_only_active_areas_of_approved_artists(self):
        self._add(city='Lucknow', travel_charge_type='free')
        off_id = self._add(city='Agra', travel_charge_type='free').data['data']['area_id']
        self.client_a.put('/artists/service_areas/update/', {'area_id': off_id, 'is_active': False}, format='json')
        customer, _ = make_customer(phone_number='+919000002104')
        rows = customer.get('/artists/service_areas/get_all/', {'artist_id': self.profile_a.artist_id}).data['data']
        self.assertEqual([r['city'] for r in rows], ['Lucknow'])


class BookingTotalsTest(TestCase):
    url = '/customers/bookings/create/'

    def setUp(self):
        seed_booking_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000002200')
        self.sub = make_sub_category()
        self.package = make_package(self.profile, sub_category=self.sub, price=2000, duration=60)
        self.home = make_location_type('Home Visit')
        make_location_preference(self.profile, self.home)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday(), start='09:00:00', end='18:00:00')
        self.customer, self.customer_user = make_customer(phone_number='+919000002201')

    def _addon(self, price='500.00', duration=30, **extra):
        return PackageAddOn.objects.create(
            artist=self.profile, name=extra.pop('name', 'Hair styling'), price=Decimal(price),
            duration_minutes=duration, **extra,
        )

    def _book(self, addon_ids=None, start='10:00:00', address=None, **extra):
        payload = {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.home.location_type_id, 'booking_date': self.date.strftime('%d-%m-%y'),
            'start_time': start, **extra,
        }
        if addon_ids is not None:
            payload['addon_ids'] = addon_ids
        if address is not None:
            payload['address_id'] = address.address_id
        return self.customer.post(self.url, payload, format='json')

    # --- add-ons
    def test_total_and_duration_include_selected_addons_and_are_snapshotted(self):
        addon = self._addon(); addon.packages.add(self.package)
        second = self._addon(price='300.00', duration=15, name='Draping'); second.packages.add(self.package)
        resp = self._book(addon_ids=[addon.addon_id, second.addon_id])
        self.assertEqual(resp.status_code, 201)
        booking = Booking.objects.get(booking_id=resp.data['data']['booking_id'])
        self.assertEqual(booking.total_amount, Decimal('2800.00'))
        self.assertEqual(resp.data['data']['total_amount'], '2800.00')
        self.assertEqual(str(booking.end_time), '11:45:00')
        snapshots = {item.name: (item.price, item.duration_minutes) for item in booking.addons.all()}
        self.assertEqual(snapshots, {'Hair styling': (Decimal('500.00'), 30), 'Draping': (Decimal('300.00'), 15)})

    def test_snapshot_survives_editing_and_deleting_the_addon(self):
        addon = self._addon(); addon.packages.add(self.package)
        booking_id = self._book(addon_ids=[addon.addon_id]).data['data']['booking_id']
        self.artist_client.put('/artists/addons/update/', {'addon_id': addon.addon_id, 'price': '999.00', 'name': 'Renamed'}, format='json')
        self.artist_client.delete(f'/artists/addons/delete/?addon_id={addon.addon_id}')
        booking = Booking.objects.get(booking_id=booking_id)
        item = booking.addons.get()
        self.assertEqual((item.name, item.price, item.addon_id), ('Hair styling', Decimal('500.00'), None))
        self.assertEqual(booking.total_amount, Decimal('2500.00'))

    def test_unavailable_addons_are_rejected_and_nothing_is_created(self):
        unlinked = self._addon(name='Unlinked')
        inactive = self._addon(name='Inactive', is_active=False); inactive.packages.add(self.package)
        _, _, other_profile = make_artist(phone_number='+919000002202')
        foreign = PackageAddOn.objects.create(artist=other_profile, name='Foreign', price=Decimal('100'))
        other_package = make_package(self.profile, name='Other pkg')
        wrong_package = self._addon(name='Other package only'); wrong_package.packages.add(other_package)
        for ids in ([unlinked.addon_id], [inactive.addon_id], [foreign.addon_id], [wrong_package.addon_id], [999999]):
            self.assertEqual(self._book(addon_ids=ids).status_code, 400, ids)
        self.assertEqual(Booking.objects.count(), 0)

    def test_client_cannot_set_the_price(self):
        resp = self._book(total_amount='1', price='1', travel_fee='0', platform_fee='0')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2000.00'))

    def test_addon_duration_extends_the_slot_for_conflict_and_schedule_checks(self):
        addon = self._addon(duration=120); addon.packages.add(self.package)
        self.assertEqual(self._book(start='10:00:00').status_code, 201)                       # 10:00-11:00
        # 09:30 + 60 + 120 = 12:30 would run over the 10:00 booking
        self.assertEqual(self._book(start='09:30:00', addon_ids=[addon.addon_id]).status_code, 400)
        # 16:30 + 60 + 120 = 19:30 is past the 18:00 end of the working day ...
        self.assertEqual(self._book(start='16:30:00', addon_ids=[addon.addon_id]).status_code, 400)
        # ... while the same slot without the add-on (ends 17:30) is fine
        self.assertEqual(self._book(start='16:30:00').status_code, 201)

    def test_duplicate_addon_ids_count_once(self):
        addon = self._addon(); addon.packages.add(self.package)
        resp = self._book(addon_ids=[addon.addon_id, addon.addon_id])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2500.00'))

    # --- exposure
    def test_customer_sees_addons_and_travel_fee_but_never_the_artists_earnings_figures(self):
        addon = self._addon(); addon.packages.add(self.package)
        booking_id = self._book(addon_ids=[addon.addon_id]).data['data']['booking_id']
        data = self.customer.get('/customers/bookings/get/', {'booking_id': booking_id}).data['data']
        self.assertEqual(data['totalAmount'], '2500.00')
        self.assertEqual(data['travelFee'], '0.00')
        self.assertEqual([item['name'] for item in data['addOns']], ['Hair styling'])
        for private in ('platformFee', 'netAmount', 'travelMinutesBefore', 'returnBufferMinutes'):
            self.assertNotIn(private, data)
        listed = self.customer.get('/customers/bookings/get_all/').data['data']['data'][0]
        self.assertEqual(listed['addOns'][0]['price'], '500.00')
        self.assertNotIn('platformFee', listed)

    def test_artist_sees_platform_fee_net_and_buffers(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(
            commission_rate=Decimal('12.50'), travel_time_before_minutes=45, return_buffer_minutes=20,
        )
        addon = self._addon(); addon.packages.add(self.package)
        booking_id = self._book(addon_ids=[addon.addon_id]).data['data']['booking_id']
        data = self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id}).data['data']
        self.assertEqual((data['totalAmount'], data['platformFee'], data['netAmount']), ('2500.00', '312.50', '2187.50'))
        self.assertEqual((data['travelMinutesBefore'], data['returnBufferMinutes']), (45, 20))
        self.assertEqual(data['addOns'][0]['name'], 'Hair styling')
        listed = self.artist_client.get('/artists/bookings/get_all/').data['data']['data'][0]
        self.assertEqual(listed['netAmount'], '2187.50')

    def test_unknown_values_column_is_still_rejected(self):
        booking_id = self._book().data['data']['booking_id']
        bad = self.artist_client.get('/artists/bookings/get/', {'booking_id': booking_id, 'values': 'nonsense'})
        self.assertEqual(bad.status_code, 400)

    def test_old_bookings_without_snapshots_still_load(self):
        from tests.test_customers import make_booking
        booking = make_booking(self.customer_user, self.profile, self.package, self.home, self.date, '10:00', '11:00')
        data = self.artist_client.get('/artists/bookings/get/', {'booking_id': booking.booking_id}).data['data']
        self.assertEqual(data['travelFee'], '0.00')
        self.assertIsNone(data['platformFee'])
        self.assertEqual(data['addOns'], [])

    # --- travel
    def test_per_visit_travel_fee_added_for_home_visit_in_covered_city(self):
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        address = make_address_in(self.customer_user, ' lucknow')
        resp = self._book(address=address)
        self.assertEqual(resp.status_code, 201)
        booking = Booking.objects.get()
        self.assertEqual((booking.travel_fee, booking.total_amount), (Decimal('250.00'), Decimal('2250.00')))
        self.assertEqual(resp.data['data']['travel_fee'], '250.00')
        data = self.customer.get('/customers/bookings/get/', {'booking_id': booking.booking_id}).data['data']
        self.assertEqual(data['travelFee'], '250.00')

    def test_free_area_adds_nothing(self):
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='free')
        self.assertEqual(self._book(address=make_address_in(self.customer_user, 'Lucknow')).status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2000.00'))

    def test_uncovered_city_or_missing_address_is_refused_once_areas_exist(self):
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='free')
        self.assertEqual(self._book(address=make_address_in(self.customer_user, 'Delhi')).status_code, 400)
        self.assertEqual(self._book().status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_inactive_area_is_ignored_and_artist_without_areas_is_unrestricted(self):
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit',
                                         charge_amount=Decimal('250'), is_active=False)
        self.assertEqual(self._book(address=make_address_in(self.customer_user, 'Delhi')).status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2000.00'))

    def test_non_home_visit_locations_are_not_charged_or_restricted(self):
        studio = make_location_type('Studio Visit')
        make_location_preference(self.profile, studio)
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        resp = self.customer.post(self.url, {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': studio.location_type_id, 'booking_date': self.date.strftime('%d-%m-%y'),
            'start_time': '10:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2000.00'))

    def test_changing_the_area_later_does_not_change_existing_booking(self):
        area = ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        booking_id = self._book(address=make_address_in(self.customer_user, 'Lucknow')).data['data']['booking_id']
        self.artist_client.put('/artists/service_areas/update/', {'area_id': area.area_id, 'charge_amount': '900'}, format='json')
        booking = Booking.objects.get(booking_id=booking_id)
        self.assertEqual((booking.travel_fee, booking.total_amount), (Decimal('250.00'), Decimal('2250.00')))

    def test_travel_and_addons_combine(self):
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        addon = self._addon(); addon.packages.add(self.package)
        self.assertEqual(self._book(addon_ids=[addon.addon_id], address=make_address_in(self.customer_user, 'Lucknow')).status_code, 201)
        self.assertEqual(Booking.objects.get().total_amount, Decimal('2750.00'))

    # --- payment consistency
    def test_payment_charges_the_booking_total_and_uses_the_booking_commission_snapshot(self):
        seed_payment_statuses()
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(commission_rate=Decimal('10.00'))
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        addon = self._addon(); addon.packages.add(self.package)
        booking_id = self._book(addon_ids=[addon.addon_id], address=make_address_in(self.customer_user, 'Lucknow')).data['data']['booking_id']
        # the artist's rate changes AFTER the booking was quoted
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(commission_rate=Decimal('25.00'))
        with patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client') as get_client:
            get_client.return_value.order.create.return_value = {'id': 'order_test_1'}
            resp = self.customer.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        payment = Payment.objects.get(booking_id=booking_id)
        self.assertEqual(payment.amount, Decimal('2750.00'))
        self.assertEqual(payment.commission_amount, Decimal('275.00'))       # 10% snapshot, not the new 25%
        self.assertEqual(payment.artist_payout_amount, Decimal('2475.00'))
        booking = Booking.objects.get(booking_id=booking_id)
        self.assertEqual((booking.platform_fee, booking.net_amount), (Decimal('275.00'), Decimal('2475.00')))


class ProfileTravelBufferTest(TestCase):
    def test_artist_sets_and_reads_buffers_and_others_do_not_see_them(self):
        client, _, profile = make_artist(phone_number='+919000002300')
        resp = client.put('/artists/profile/update/', {'travel_time_before_minutes': 40, 'return_buffer_minutes': 15}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = client.get('/artists/profile/get/').data['data']
        self.assertEqual((data['travelTimeBeforeMinutes'], data['returnBufferMinutes']), (40, 15))
        customer, _ = make_customer(phone_number='+919000002301')
        public = customer.get('/artists/profile/get/', {'artist_id': profile.artist_id}).data['data']
        self.assertNotIn('travelTimeBeforeMinutes', public)
        self.assertEqual(client.put('/artists/profile/update/', {'return_buffer_minutes': 999}, format='json').status_code, 400)



class TravelBufferTest(TestCase):
    """Home Visit appointments block extra time around them: travel before, return after."""
    url = '/customers/bookings/create/'

    def setUp(self):
        seed_booking_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000002400')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(
            travel_time_before_minutes=30, return_buffer_minutes=15)
        self.package = make_package(self.profile, price=1000, duration=60)
        self.home = make_location_type('Home Visit')
        self.studio = make_location_type('Studio')
        make_location_preference(self.profile, self.home)
        make_location_preference(self.profile, self.studio)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday(), start='06:00:00', end='22:00:00')
        self.customer, self.customer_user = make_customer(phone_number='+919000002401')

    def _book(self, start, location=None, customer=None):
        return (customer or self.customer).post(self.url, {
            'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': (location or self.home).location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': start,
        }, format='json')

    def test_snapshots_are_taken_only_for_home_visits(self):
        home = self._book('10:00:00').data['data']['booking_id']
        studio = self._book('15:00:00', location=self.studio).data['data']['booking_id']
        self.assertEqual((Booking.objects.get(booking_id=home).travel_minutes_before, Booking.objects.get(booking_id=home).return_buffer_minutes), (30, 15))
        self.assertEqual((Booking.objects.get(booking_id=studio).travel_minutes_before, Booking.objects.get(booking_id=studio).return_buffer_minutes), (0, 0))

    def test_next_home_visit_needs_return_plus_travel_gap(self):
        self.assertEqual(self._book('10:00:00').status_code, 201)            # 10:00-11:00, occupies 09:30-11:15
        self.assertEqual(self._book('11:15:00').status_code, 400)            # own travel starts 10:45 -> clash
        self.assertEqual(self._book('11:30:00').status_code, 400)            # travel starts 11:00 -> clash
        self.assertEqual(self._book('11:45:00').status_code, 201)            # travel starts 11:15 == end of window -> ok

    def test_booking_before_an_existing_one_also_needs_room(self):
        self.assertEqual(self._book('12:00:00').status_code, 201)            # occupies 11:30-13:15
        self.assertEqual(self._book('10:30:00').status_code, 400)            # 10:30-11:30 + 15 return = 11:45 > 11:30 -> clash
        self.assertEqual(self._book('09:45:00').status_code, 201)            # ends 10:45 + 15 = 11:00 <= 11:30

    def test_exact_touching_windows_are_allowed(self):
        self.assertEqual(self._book('10:00:00').status_code, 201)            # window ends 11:15
        self.assertEqual(self._book('11:45:00').status_code, 201)            # window starts 11:15
        self.assertEqual(Booking.objects.count(), 2)

    def test_studio_booking_after_a_home_visit_still_waits_for_the_return_trip(self):
        self.assertEqual(self._book('10:00:00').status_code, 201)            # return trip until 11:15
        self.assertEqual(self._book('11:05:00', location=self.studio).status_code, 400)
        self.assertEqual(self._book('11:15:00', location=self.studio).status_code, 201)

    def test_home_visit_after_a_studio_booking_needs_travel_time(self):
        self.assertEqual(self._book('10:00:00', location=self.studio).status_code, 201)   # no buffers, ends 11:00
        self.assertEqual(self._book('11:15:00').status_code, 400)            # travel from 10:45
        self.assertEqual(self._book('11:30:00').status_code, 201)

    def test_two_studio_bookings_behave_exactly_as_before(self):
        self.assertEqual(self._book('10:00:00', location=self.studio).status_code, 201)
        self.assertEqual(self._book('11:00:00', location=self.studio).status_code, 201)   # back-to-back is fine
        self.assertEqual(self._book('10:30:00', location=self.studio).status_code, 400)

    def test_zero_buffers_keep_the_old_back_to_back_behaviour(self):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(travel_time_before_minutes=0, return_buffer_minutes=0)
        self.assertEqual(self._book('10:00:00').status_code, 201)
        self.assertEqual(self._book('11:00:00').status_code, 201)

    def test_cancelled_bookings_release_their_buffers(self):
        booking_id = self._book('10:00:00').data['data']['booking_id']
        self.assertEqual(self._book('11:15:00').status_code, 400)
        Booking.objects.filter(booking_id=booking_id).update(status=type(Booking.objects.get(booking_id=booking_id).status).objects.get(name='cancelled'))
        self.assertEqual(self._book('11:15:00').status_code, 201)

    def test_changing_the_artists_buffers_does_not_move_existing_bookings(self):
        self.assertEqual(self._book('10:00:00').status_code, 201)            # snapshot 30/15
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(travel_time_before_minutes=0, return_buffer_minutes=0)
        # the old booking still occupies 09:30-11:15, a zero-buffer home visit just needs to clear that
        self.assertEqual(self._book('11:00:00').status_code, 400)
        self.assertEqual(self._book('11:15:00').status_code, 201)

    def test_legacy_bookings_without_snapshots_count_as_zero_buffers(self):
        from tests.test_customers import make_booking
        make_booking(self.customer_user, self.profile, self.package, self.studio, self.date, '10:00', '11:00', status_name='confirmed')
        self.assertIsNone(Booking.objects.get().travel_minutes_before)
        self.assertEqual(self._book('11:15:00').status_code, 400)            # own travel (30) still applies
        self.assertEqual(self._book('11:30:00').status_code, 201)

    def test_availability_endpoint_shows_blocked_windows_and_buffers(self):
        self._book('10:00:00')
        data = self.customer.get('/customers/artists/availability/', {
            'artist_id': self.profile.artist_id, 'booking_date': self.date.strftime('%d-%m-%y')}).data['data']
        self.assertEqual([(str(r['startTime']), str(r['endTime'])) for r in data['bookedRanges']], [('10:00:00', '11:00:00')])
        self.assertEqual([(str(r['startTime']), str(r['endTime'])) for r in data['blockedRanges']], [('09:30:00', '11:15:00')])
        self.assertEqual((data['bufferBeforeMinutes'], data['bufferAfterMinutes']), (30, 15))

    def test_reschedule_respects_buffers_and_ignores_the_booking_itself(self):
        confirmed = Booking.objects.get(booking_id=self._book('10:00:00').data['data']['booking_id'])
        Booking.objects.filter(booking_id=confirmed.booking_id).update(status=type(confirmed.status).objects.get(name='confirmed'))
        other = self._book('14:00:00', customer=make_customer(phone_number='+919000002402')[0]).data['data']['booking_id']
        Booking.objects.filter(booking_id=other).update(status=type(confirmed.status).objects.get(name='confirmed'))
        request = lambda start: self.artist_client.post('/artists/bookings/reschedule/request/', {
            'booking_id': confirmed.booking_id, 'proposed_date': self.date.strftime('%d-%m-%y'),
            'proposed_start_time': start}, format='json')
        self.assertEqual(request('12:30:00').status_code, 400)               # 12:30-13:30 +15 = 13:45 vs other's 13:30 start -> clash
        self.assertEqual(request('11:45:00').status_code, 201)               # 11:45-12:45, window 11:15-13:00 fits before 13:30
        reschedule = BookingReschedule.objects.get()
        self.assertEqual(self.customer.put('/customers/bookings/reschedule/respond/', {
            'reschedule_id': reschedule.reschedule_id, 'decision': 'accepted'}, format='json').status_code, 200)
