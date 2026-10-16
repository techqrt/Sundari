"""paymentStatus=paid|unpaid filter on the booking lists and single-booking gets (artist and customer)."""
from django.test import TestCase

from sunndari_apps.customers.models import Booking

from tests.test_customers import (
    make_artist, make_customer, make_sub_category, make_package, make_location_type, make_booking,
    make_paid_payment, next_weekday,
)


class BookingPaymentFilterTest(TestCase):
    def setUp(self):
        self.artist_client, _, self.profile = make_artist(phone_number='+919000008001')
        self.customer_client, self.customer = make_customer(phone_number='+919000008002')
        package = make_package(self.profile, sub_category=make_sub_category())
        location = make_location_type()
        day = next_weekday(2)
        self.paid = make_booking(self.customer, self.profile, package, location, day, '09:00:00', '10:00:00')
        self.unpaid = make_booking(self.customer, self.profile, package, location, day, '12:00:00', '13:00:00')
        self.unpaid_two = make_booking(self.customer, self.profile, package, location, day, '15:00:00', '16:00:00')
        make_paid_payment(self.paid)

    def ids(self, client, url, **query):
        resp = client.get(url, query)
        self.assertEqual(resp.status_code, 200, resp.content)
        return sorted(row['bookingId'] for row in resp.data['data']['data'])

    def both(self):
        return (
            (self.customer_client, '/customers/bookings/get_all/'),
            (self.artist_client, '/artists/bookings/get_all/'),
        )

    def test_no_filter_returns_everything(self):
        for client, url in self.both():
            self.assertEqual(len(self.ids(client, url)), 3)

    def test_paid_returns_only_paid_bookings(self):
        for client, url in self.both():
            self.assertEqual(self.ids(client, url, filter_key='paymentStatus', filter_value='paid'), [self.paid.booking_id])

    def test_unpaid_returns_only_unpaid_bookings(self):
        for client, url in self.both():
            self.assertEqual(self.ids(client, url, filter_key='paymentStatus', filter_value='unpaid'),
                             sorted([self.unpaid.booking_id, self.unpaid_two.booking_id]))

    def test_snake_case_key_and_any_letter_case_work(self):
        for client, url in self.both():
            self.assertEqual(self.ids(client, url, filter_key='payment_status', filter_value='PAID'), [self.paid.booking_id])

    def test_a_failed_or_pending_payment_does_not_count_as_paid(self):
        from sunndari_apps.payments.models import Payment
        from sunndari_apps.core.models.payment_status import PaymentStatus
        PaymentStatus.objects.get_or_create(name='failed', defaults={'description': 'failed'})
        Payment.objects.filter(booking_id=self.paid.booking_id).update(
            status_id=PaymentStatus.objects.get(name='failed').status_id)
        for client, url in self.both():
            self.assertEqual(self.ids(client, url, filter_key='paymentStatus', filter_value='paid'), [])

    def test_bad_value_is_a_400(self):
        for client, url in self.both():
            resp = client.get(url, {'filter_key': 'paymentStatus', 'filter_value': 'maybe'})
            self.assertEqual(resp.status_code, 400)

    def test_combines_with_other_filters_and_pagination(self):
        resp = self.customer_client.get('/customers/bookings/get_all/', {
            'filter_key': 'paymentStatus', 'filter_value': 'unpaid', 'limit': 1, 'page_num': 2})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['totalPage'], 2)
        self.assertEqual(len(resp.data['data']['data']), 1)

    def test_other_users_bookings_never_leak_through_the_filter(self):
        other_client, _ = make_customer(phone_number='+919000008003')
        other_artist, _, _ = make_artist(phone_number='+919000008004')
        for client, url in ((other_client, '/customers/bookings/get_all/'), (other_artist, '/artists/bookings/get_all/')):
            self.assertEqual(self.ids(client, url, filter_key='paymentStatus', filter_value='paid'), [])

    def test_single_get_with_the_filter(self):
        for client, url in ((self.customer_client, '/customers/bookings/get/'), (self.artist_client, '/artists/bookings/get/')):
            ok = client.get(url, {'booking_id': self.paid.booking_id, 'filter_key': 'paymentStatus', 'filter_value': 'paid'})
            self.assertEqual(ok.status_code, 200, ok.content)
            miss = client.get(url, {'booking_id': self.paid.booking_id, 'filter_key': 'paymentStatus', 'filter_value': 'unpaid'})
            self.assertEqual(miss.status_code, 400)
            self.assertEqual(client.get(url, {'booking_id': self.unpaid.booking_id}).status_code, 200)    # no filter: unchanged

    def _set_payment_status(self, booking, name):
        from sunndari_apps.payments.models import Payment
        from sunndari_apps.core.models.payment_status import PaymentStatus
        PaymentStatus.objects.get_or_create(name=name, defaults={'description': name})
        Payment.objects.filter(booking_id=booking.booking_id).update(status_id=PaymentStatus.objects.get(name=name).status_id)

    def test_a_refunded_booking_is_in_neither_list(self):
        self._set_payment_status(self.paid, 'refunded')
        for client, url in self.both():
            self.assertNotIn(self.paid.booking_id, self.ids(client, url, filter_key='paymentStatus', filter_value='paid'))
            self.assertNotIn(self.paid.booking_id, self.ids(client, url, filter_key='paymentStatus', filter_value='unpaid'))

    def test_a_partially_refunded_booking_still_counts_as_paid(self):
        self._set_payment_status(self.paid, 'partially_refunded')
        for client, url in self.both():
            self.assertEqual(self.ids(client, url, filter_key='paymentStatus', filter_value='paid'), [self.paid.booking_id])

    def test_hostile_filter_values_are_rejected_not_executed(self):
        for client, url in self.both():
            for value in ("paid' OR '1'='1", "paid;DROP TABLE bookings", "", "%", "unpaid%"):
                resp = client.get(url, {'filter_key': 'paymentStatus', 'filter_value': value})
                self.assertIn(resp.status_code, (200, 400), value)
                if resp.status_code == 200:                       # '' means "no filter"; the rest must have been refused
                    self.assertEqual(value, '', value)
        self.assertEqual(Booking.objects.count(), 3)
