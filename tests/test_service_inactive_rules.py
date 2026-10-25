"""Task 3 of the service-activation feature: what a switched-off service means for everyone else.

Rules (agreed): a service is *live* when it AND its category are active. Customers and artists no longer see,
search, attach to, or newly book a service that is not live; admins still see everything; and nothing that
already exists is touched - bookings keep working and an artist keeps their own data. Switching a service off
never switches its parent category off."""
from unittest.mock import patch, MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from sunndari_apps.artists.models import ArtistServiceOffering, ArtistSpeciality, PricingPackage
from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.customers.models import Booking

from tests.test_artists import make_image_bytes
from tests.test_customers import (
    make_artist, make_customer, make_location_type, make_location_preference, make_package, make_schedule,
    next_weekday, seed_booking_statuses, seed_payment_statuses,
)
from tests.test_help_center import make_admin


class _Fixture(TestCase):
    """Category 'Makeup' with two services - Bridal (stays live) and Party (gets switched off)."""

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        self.makeup = ServiceCategory.objects.create(name='Makeup')
        self.hair = ServiceCategory.objects.create(name='Hair')
        self.bridal = ServiceSubCategory.objects.create(category=self.makeup, name='Bridal Makeup')
        self.party = ServiceSubCategory.objects.create(category=self.makeup, name='Party Makeup')
        self.cut = ServiceSubCategory.objects.create(category=self.hair, name='Haircut')
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919500000001')
        self.customer_client, self.customer = make_customer(phone_number='+919500000002')
        self.admin_client, _ = make_admin(phone_number='+919500000003')
        self.location = make_location_type()
        make_location_preference(self.profile, self.location)
        self.day = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.day.weekday())
        self.bridal_pkg = make_package(self.profile, sub_category=self.bridal, price=3000, name='Bridal Package')
        self.party_pkg = make_package(self.profile, sub_category=self.party, price=1000, name='Party Package')

    def switch(self, service, active):
        service.is_active = active
        service.save()
        service.refresh_from_db()

    def names(self, client, url, **params):
        resp = client.get(url, params)
        self.assertEqual(resp.status_code, 200, resp.data)
        return [row['name'] for row in resp.data['data']['data']]

    def book(self, package, client=None):
        return (client or self.customer_client).post('/customers/bookings/create/', {
            'artist_id': self.profile.artist_id, 'package_id': package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.day.strftime('%d-%m-%y'), 'start_time': '10:00:00',
        }, format='json')


# ─── Pick-lists ───────────────────────────────────────────────────────────────

class ListingTest(_Fixture):
    SUBS, CATS = '/core/service-sub-category/get_all/', '/core/service-category/get_all/'

    def test_a_switched_off_service_leaves_customer_and_artist_lists_but_not_the_admins(self):
        self.switch(self.party, False)
        for client in (self.customer_client, self.artist_client):
            shown = self.names(client, self.SUBS)
            self.assertNotIn('Party Makeup', shown)
            self.assertIn('Bridal Makeup', shown)
        self.assertIn('Party Makeup', self.names(self.admin_client, self.SUBS))

    def test_switching_a_service_off_never_switches_its_category_off(self):
        self.switch(self.party, False)
        self.assertTrue(ServiceCategory.objects.get(pk=self.makeup.pk).is_active)
        self.assertIn('Makeup', self.names(self.customer_client, self.CATS))
        self.assertIn('Bridal Makeup', self.names(self.customer_client, self.SUBS))        # its sibling is untouched

    def test_a_category_switched_off_hides_its_services_without_editing_them(self):
        self.makeup.is_active = False
        self.makeup.save()
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.bridal.pk).is_active)         # not rewritten
        shown = self.names(self.customer_client, self.SUBS)
        self.assertEqual(shown, ['Haircut'])
        self.assertNotIn('Makeup', self.names(self.customer_client, self.CATS))
        self.assertIn('Makeup', self.names(self.admin_client, self.CATS))
        self.assertIn('Bridal Makeup', self.names(self.admin_client, self.SUBS))

    def test_switching_it_back_on_brings_it_back(self):
        self.switch(self.party, False)
        self.switch(self.party, True)
        self.assertIn('Party Makeup', self.names(self.customer_client, self.SUBS))

    def test_a_switched_off_service_can_still_be_looked_up_by_id_so_old_references_resolve(self):
        self.switch(self.party, False)
        resp = self.customer_client.get('/core/service-sub-category/get/', {'sub_category_id': self.party.sub_category_id})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['data']['isActive'])


# ─── Discovery ────────────────────────────────────────────────────────────────

class DiscoveryTest(_Fixture):
    SEARCH = '/customers/artists/search/'

    def found(self, **params):
        return [row['artistId'] for row in self.customer_client.get(self.SEARCH, params).data['data']['data']]

    def test_an_artist_is_found_through_a_live_service_and_not_through_a_switched_off_one(self):
        self.assertIn(self.profile.artist_id, self.found(sub_category_id=self.party.sub_category_id))
        self.switch(self.party, False)
        self.assertNotIn(self.profile.artist_id, self.found(sub_category_id=self.party.sub_category_id))
        self.assertIn(self.profile.artist_id, self.found(sub_category_id=self.bridal.sub_category_id))

    def test_the_starting_price_ignores_packages_under_a_switched_off_service(self):
        self.switch(self.party, False)                                  # the cheaper ₹1000 package is no longer bookable
        row = self.customer_client.get(self.SEARCH).data['data']['data'][0]
        self.assertEqual(float(row['startingPrice']), 3000.0)

    def test_an_artist_whose_every_package_is_switched_off_disappears_from_search(self):
        self.switch(self.party, False)
        self.switch(self.bridal, False)
        self.assertEqual(self.found(), [])
        self.assertEqual(self.found(category_id=self.makeup.category_id), [])
        self.switch(self.bridal, True)
        self.assertEqual(self.found(), [self.profile.artist_id])

    def test_a_category_switched_off_hides_the_artists_under_it(self):
        self.makeup.is_active = False
        self.makeup.save()
        self.assertEqual(self.found(), [])

    def test_the_artist_page_lists_only_bookable_packages_and_services(self):
        ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=self.bridal.sub_category_id)
        ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=self.party.sub_category_id)
        self.switch(self.party, False)
        data = self.customer_client.get('/customers/artists/get/', {'artist_id': self.profile.artist_id}).data['data']
        self.assertEqual([p['name'] for p in data['packages']], ['Bridal Package'])
        self.assertEqual([s['subCategoryId'] for s in data['services']], [self.bridal.sub_category_id])

    def test_the_public_page_and_specialities_hide_it_too_but_the_artist_still_sees_their_own(self):
        for service in (self.bridal, self.party):
            ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=service.sub_category_id)
        ArtistSpeciality.replace_for_artist(artist_id=self.profile.artist_id,
                                            sub_category_ids=[self.bridal.sub_category_id, self.party.sub_category_id])
        self.switch(self.party, False)
        from sunndari_apps.artists.models import ArtistProfile
        slug = ArtistProfile.ensure_public_slug(user_id=self.artist_user.user_id)
        public = self.customer_client.get('/public/artists/get/', {'slug': slug}).data['data']
        self.assertEqual(public['specialities'], ['Bridal Makeup'])
        self.assertEqual([p['name'] for p in public['packages']], ['Bridal Package'])
        seen_by_customer = self.customer_client.get('/artists/profile/specialities/get_all/', {'artist_id': self.profile.artist_id})
        self.assertEqual([s['name'] for s in seen_by_customer.data['data']], ['Bridal Makeup'])
        own = self.artist_client.get('/artists/profile/specialities/get_all/')
        self.assertEqual(sorted(s['name'] for s in own.data['data']), ['Bridal Makeup', 'Party Makeup'])


# ─── Artists: nothing NEW on a switched-off service ───────────────────────────

class ArtistRulesTest(_Fixture):

    def setUp(self):
        super().setUp()
        self.switch(self.party, False)

    def test_cannot_offer_or_specialise_in_a_switched_off_service(self):
        resp = self.artist_client.post('/artists/services/add/', {'sub_category_id': self.party.sub_category_id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('unavailable', resp.data['message'].lower() + str(resp.data.get('error')).lower())
        self.assertFalse(ArtistServiceOffering.objects.filter(artist_id=self.profile.artist_id).exists())
        self.assertEqual(self.artist_client.post('/artists/services/add/', {'sub_category_id': self.bridal.sub_category_id},
                                                 format='json').status_code, 201)         # a live one is fine

    def test_cannot_pick_a_new_speciality_but_may_keep_one_they_already_have(self):
        ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=self.bridal.sub_category_id)
        ArtistServiceOffering.add(artist_id=self.profile.artist_id, sub_category_id=self.party.sub_category_id)
        put = lambda ids: self.artist_client.put('/artists/profile/specialities/set/', {'sub_category_ids': ids}, format='json')
        self.assertEqual(put([self.party.sub_category_id]).status_code, 400)               # new, and switched off
        ArtistSpeciality.replace_for_artist(artist_id=self.profile.artist_id, sub_category_ids=[self.party.sub_category_id])
        self.assertEqual(put([self.party.sub_category_id, self.bridal.sub_category_id]).status_code, 200)   # keeps it, adds a live one

    def test_cannot_create_a_package_under_a_switched_off_service(self):
        before = PricingPackage.objects.count()
        resp = self.artist_client.post('/artists/packages/create/', {
            'sub_category_id': self.party.sub_category_id, 'name': 'New', 'price': '2000.00', 'duration_minutes': 60}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PricingPackage.objects.count(), before)

    def test_can_still_edit_an_existing_package_under_it_but_cannot_move_one_onto_it(self):
        edit = self.artist_client.put('/artists/packages/update/', {'package_id': self.party_pkg.package_id, 'price': '1200.00'}, format='json')
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(str(PricingPackage.objects.get(pk=self.party_pkg.pk).price), '1200.00')
        move = self.artist_client.put('/artists/packages/update/', {
            'package_id': self.bridal_pkg.package_id, 'sub_category_id': self.party.sub_category_id}, format='json')
        self.assertEqual(move.status_code, 400)
        self.assertEqual(PricingPackage.objects.get(pk=self.bridal_pkg.pk).sub_category_id, self.bridal.sub_category_id)

    def test_the_artist_still_sees_all_of_their_own_packages(self):
        names = [p['name'] for p in self.artist_client.get('/artists/packages/get_all/').data['data']['data']]
        self.assertEqual(sorted(names), ['Bridal Package', 'Party Package'])

    def test_portfolio_items_cannot_be_tagged_with_a_switched_off_service(self):
        upload = lambda sub: self.artist_client.post('/artists/portfolio/create/', {
            'media_type': 'image', 'sub_category_id': sub.sub_category_id,
            'file': SimpleUploadedFile('w.jpg', make_image_bytes('JPEG'), content_type='image/jpeg')}, format='multipart')
        self.assertEqual(upload(self.party).status_code, 400)
        self.assertEqual(upload(self.bridal).status_code, 201)


# ─── Bookings ─────────────────────────────────────────────────────────────────

class BookingRulesTest(_Fixture):

    def setUp(self):
        super().setUp()
        patcher = patch('sunndari_apps.payments.views.initiate_payment.RazorpayGateway.get_client')
        client = patcher.start()
        self.addCleanup(patcher.stop)
        gateway = MagicMock()
        gateway.order.create.side_effect = lambda data: {'id': f"order_{data['receipt']}", 'amount': data['amount'],
                                                         'currency': data['currency'], 'status': 'created'}
        client.return_value = gateway

    def test_a_new_booking_cannot_be_made_for_a_switched_off_service(self):
        self.switch(self.party, False)
        resp = self.book(self.party_pkg)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Booking.objects.exists())
        self.assertEqual(self.book(self.bridal_pkg).status_code, 201)                  # a live service still books

    def test_a_new_booking_cannot_be_made_while_the_category_is_switched_off(self):
        self.makeup.is_active = False
        self.makeup.save()
        self.assertEqual(self.book(self.bridal_pkg).status_code, 400)

    def test_a_booking_made_before_the_switch_off_keeps_working(self):
        booking_id = self.book(self.party_pkg).data['data']['booking_id']
        self.switch(self.party, False)
        self.assertEqual(self.customer_client.get('/customers/bookings/get/', {'booking_id': booking_id}).status_code, 200)
        listed = self.customer_client.get('/customers/bookings/get_all/').data['data']['data']
        self.assertIn(booking_id, [b['bookingId'] for b in listed])
        self.assertEqual(self.customer_client.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json').status_code, 201)
        self.assertEqual(self.customer_client.put('/customers/bookings/cancel/', {'booking_id': booking_id}, format='json').status_code, 200)
        self.assertEqual(Booking.objects.get(booking_id=booking_id).sub_category_id, self.party.sub_category_id)   # history intact

    def test_switching_back_on_allows_new_bookings_again(self):
        self.switch(self.party, False)
        self.switch(self.party, True)
        self.assertEqual(self.book(self.party_pkg).status_code, 201)
