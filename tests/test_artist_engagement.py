from datetime import timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from sunndari_apps.customers.models import Review, CustomerReview
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import (
    make_customer, make_artist, make_package, make_sub_category, make_category, make_location_type,
    make_booking, seed_booking_statuses, next_weekday,
)


class EngagementBase(TestCase):
    def setUp(self):
        seed_booking_statuses()
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919000006000')
        self.customer_client, self.customer = make_customer(phone_number='+919000006001', name='Riya')
        self.package = make_package(self.profile, price=2000)
        self.location = make_location_type('Studio')
        self.date = next_weekday(2)

    def _booking(self, status='completed', customer=None, day_offset=0, start='10:00', end='11:00', package=None):
        return make_booking(customer or self.customer, self.profile, package or self.package, self.location,
                            self.date + timedelta(days=day_offset), start, end, status_name=status)


class ReviewReplyTest(EngagementBase):
    def _review(self, booking=None, rating=4, comment='Nice work'):
        booking = booking or self._booking()
        review_id = Review().create(booking_id=booking.booking_id, customer_id=booking.customer_id,
                                    artist_id=self.profile.artist_id, rating=rating, comment=comment)
        return review_id

    def test_artist_lists_reviews_with_customer_name(self):
        review_id = self._review()
        rows = self.artist_client.get('/artists/reviews/get_all/').data['data']['data']
        self.assertEqual([r['reviewId'] for r in rows], [review_id])
        self.assertEqual((rows[0]['customerName'], rows[0]['rating'], rows[0]['reply']), ('Riya', 4, None))

    def test_other_artists_reviews_are_not_listed(self):
        self._review()
        other, _, _ = make_artist(phone_number='+919000006002')
        self.assertEqual(other.get('/artists/reviews/get_all/').data['data']['data'], [])

    def test_reply_is_saved_visible_to_customers_and_notifies_once(self):
        review_id = self._review()
        resp = self.artist_client.put('/artists/reviews/reply/', {'review_id': review_id, 'reply': 'Thank you Riya!'}, format='json')
        self.assertEqual(resp.status_code, 200)
        shown = self.customer_client.get('/customers/reviews/get/', {'review_id': review_id}).data['data']
        self.assertEqual(shown['reply'], 'Thank you Riya!')
        self.assertIsNotNone(shown['repliedAt'])
        listed = self.customer_client.get('/customers/reviews/get_all/', {'artist_id': self.profile.artist_id}).data['data']['data']
        self.assertEqual(listed[0]['reply'], 'Thank you Riya!')
        self.artist_client.put('/artists/reviews/reply/', {'review_id': review_id, 'reply': 'Edited reply'}, format='json')
        self.assertEqual(Review.objects.get(review_id=review_id).reply, 'Edited reply')
        self.assertEqual(Notification.objects.filter(user_id=self.customer.user_id, type='review_reply').count(), 1)

    def test_only_the_reviewed_artist_can_reply(self):
        review_id = self._review()
        other, _, _ = make_artist(phone_number='+919000006003')
        self.assertEqual(other.put('/artists/reviews/reply/', {'review_id': review_id, 'reply': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.customer_client.put('/artists/reviews/reply/', {'review_id': review_id, 'reply': 'x'}, format='json').status_code, 400)
        self.assertEqual(APIClient().put('/artists/reviews/reply/', {'review_id': review_id, 'reply': 'x'}, format='json').status_code, 401)
        self.assertIsNone(Review.objects.get(review_id=review_id).reply)

    def test_reply_validation(self):
        review_id = self._review()
        for reply in ('', 'x' * 1001):
            self.assertEqual(self.artist_client.put('/artists/reviews/reply/', {'review_id': review_id, 'reply': reply}, format='json').status_code, 400)
        self.assertEqual(self.artist_client.put('/artists/reviews/reply/', {'review_id': 99999, 'reply': 'x'}, format='json').status_code, 400)


class CustomerReviewTest(EngagementBase):
    url = '/artists/customer_reviews/create/'

    def _create(self, booking, client=None, **extra):
        return (client or self.artist_client).post(self.url, {'booking_id': booking.booking_id, 'rating': 5, **extra}, format='json')

    def test_artist_reviews_customer_after_completed_booking(self):
        booking = self._booking()
        resp = self._create(booking, comment='Punctual and polite')
        self.assertEqual(resp.status_code, 201)
        review = CustomerReview.objects.get()
        self.assertEqual((review.customer_id, review.artist_id, review.rating), (self.customer.user_id, self.profile.artist_id, 5))
        rows = self.artist_client.get('/artists/customer_reviews/get_all/').data['data']['data']
        self.assertEqual((rows[0]['customerName'], rows[0]['comment']), ('Riya', 'Punctual and polite'))

    def test_only_completed_bookings_and_only_once(self):
        for status in ('pending', 'confirmed', 'in_progress', 'cancelled', 'no_show'):
            self.assertEqual(self._create(self._booking(status=status, start='12:00', end='13:00')).status_code, 400, status)
        booking = self._booking(start='14:00', end='15:00')
        self.assertEqual(self._create(booking).status_code, 201)
        self.assertEqual(self._create(booking).status_code, 400)
        self.assertEqual(CustomerReview.objects.count(), 1)

    def test_only_the_bookings_artist_can_review_and_customers_cannot(self):
        booking = self._booking()
        other, _, _ = make_artist(phone_number='+919000006004')
        self.assertEqual(self._create(booking, client=other).status_code, 400)
        self.assertEqual(self._create(booking, client=self.customer_client).status_code, 400)
        self.assertEqual(self._create(booking, client=APIClient()).status_code, 401)
        self.assertEqual(CustomerReview.objects.count(), 0)

    def test_rating_bounds(self):
        booking = self._booking()
        for rating in (0, 6, 'x'):
            self.assertEqual(self.artist_client.post(self.url, {'booking_id': booking.booking_id, 'rating': rating}, format='json').status_code, 400)

    def test_customer_review_never_touches_the_artist_reviews_or_ratings(self):
        booking = self._booking()
        self._create(booking)
        self.assertEqual(Review.objects.count(), 0)
        self.assertEqual(self.customer_client.get('/customers/reviews/get_all/', {'artist_id': self.profile.artist_id}).data['data']['data'], [])

    def test_artist_sees_only_their_own_and_can_filter_by_booking(self):
        first, second = self._booking(), self._booking(start='13:00', end='14:00')
        self._create(first); self._create(second)
        other, _, _ = make_artist(phone_number='+919000006005')
        self.assertEqual(other.get('/artists/customer_reviews/get_all/').data['data']['data'], [])
        filtered = self.artist_client.get('/artists/customer_reviews/get_all/', {
            'filter_key': 'bookingId', 'filter_value': first.booking_id}).data['data']['data']
        self.assertEqual([r['bookingId'] for r in filtered], [first.booking_id])


class ClientsAndNotesTest(EngagementBase):
    def test_clients_are_customers_with_real_bookings_with_counts(self):
        self._booking(status='completed', start='09:00', end='10:00')
        self._booking(status='completed', day_offset=1, start='09:00', end='10:00')
        self._booking(status='confirmed', day_offset=2, start='09:00', end='10:00')
        self._booking(status='pending', day_offset=3, start='09:00', end='10:00')
        _, only_pending = make_customer(phone_number='+919000006006', name='Pending Only')
        self._booking(status='pending', customer=only_pending, start='12:00', end='13:00')
        _, cancelled = make_customer(phone_number='+919000006007', name='Cancelled Only')
        self._booking(status='cancelled', customer=cancelled, start='14:00', end='15:00')
        rows = self.artist_client.get('/artists/clients/get_all/').data['data']['data']
        self.assertEqual([r['name'] for r in rows], ['Riya'])
        self.assertEqual((rows[0]['bookingsCount'], rows[0]['completedBookings']), (3, 2))
        self.assertEqual(rows[0]['lastBookingDate'], (self.date + timedelta(days=2)).isoformat())
        self.assertIsNone(rows[0]['note'])
        for private in ('phone', 'email', 'address'):
            self.assertNotIn(private, str(rows[0]).lower())

    def test_note_set_update_clear_and_shown_in_listing(self):
        self._booking()
        url = '/artists/clients/note/set/'
        self.assertEqual(self.artist_client.put(url, {'customer_id': self.customer.user_id, 'note': 'Allergic to latex'}, format='json').status_code, 200)
        row = self.artist_client.get('/artists/clients/get_all/').data['data']['data'][0]
        self.assertEqual(row['note'], 'Allergic to latex')
        self.artist_client.put(url, {'customer_id': self.customer.user_id, 'note': 'Prefers evenings'}, format='json')
        self.assertEqual(self.artist_client.get('/artists/clients/get_all/').data['data']['data'][0]['note'], 'Prefers evenings')
        self.artist_client.put(url, {'customer_id': self.customer.user_id, 'note': '  '}, format='json')
        self.assertIsNone(self.artist_client.get('/artists/clients/get_all/').data['data']['data'][0]['note'])

    def test_notes_are_private_per_artist_and_need_a_real_client(self):
        self._booking()
        url = '/artists/clients/note/set/'
        other, _, other_profile = make_artist(phone_number='+919000006008')
        self.assertEqual(other.put(url, {'customer_id': self.customer.user_id, 'note': 'x'}, format='json').status_code, 400)
        self.artist_client.put(url, {'customer_id': self.customer.user_id, 'note': 'secret'}, format='json')
        self.assertEqual(other.get('/artists/clients/get_all/').data['data']['data'], [])
        self.assertEqual(self.artist_client.put(url, {'customer_id': 999999, 'note': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.customer_client.put(url, {'customer_id': self.customer.user_id, 'note': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.artist_client.put(url, {'customer_id': self.customer.user_id, 'note': 'x' * 1001}, format='json').status_code, 400)
        self.assertEqual(APIClient().get('/artists/clients/get_all/').status_code, 401)

    def test_search_and_sort(self):
        self._booking(start='09:00', end='10:00')
        _, other_user = make_customer(phone_number='+919000006009', name='Anita')
        self._booking(customer=other_user, day_offset=1, start='09:00', end='10:00')
        by_name = self.artist_client.get('/artists/clients/get_all/', {'sort_by': 'name', 'sort_order': 'asc'}).data['data']['data']
        self.assertEqual([r['name'] for r in by_name], ['Anita', 'Riya'])
        recent_first = self.artist_client.get('/artists/clients/get_all/').data['data']['data']
        self.assertEqual([r['name'] for r in recent_first], ['Anita', 'Riya'])
        found = self.artist_client.get('/artists/clients/get_all/', {'search_key': 'riy'}).data['data']['data']
        self.assertEqual([r['name'] for r in found], ['Riya'])


class InsightsTest(EngagementBase):
    url = '/artists/insights/summary/'

    def test_summary_counts_repeat_clients_top_services_and_views(self):
        other_sub = make_sub_category(category=make_category(name='Hair'), name='Hair styling')
        other_package = make_package(self.profile, sub_category=other_sub, name='Hair', price=800)
        _, second_customer = make_customer(phone_number='+919000006010', name='Meera')
        self._booking(status='completed', start='09:00', end='10:00')
        self._booking(status='completed', day_offset=1, start='09:00', end='10:00')
        self._booking(status='completed', customer=second_customer, day_offset=2, start='09:00', end='10:00', package=other_package)
        self._booking(status='cancelled', day_offset=3, start='09:00', end='10:00')
        self._booking(status='pending', day_offset=4, start='09:00', end='10:00')
        type(self.profile).objects.filter(artist_id=self.profile.artist_id).update(profile_view_count=42)
        data = self.artist_client.get(self.url).data['data']
        self.assertEqual(data['totalBookings'], 5)
        self.assertEqual((data['completedBookings'], data['cancelledBookings']), (3, 1))
        self.assertEqual(data['bookingsByStatus'], {'completed': 3, 'cancelled': 1, 'pending': 1})
        self.assertEqual(data['repeatClients'], 1)
        self.assertEqual([(s['name'], s['bookings']) for s in data['topServices']], [(self.package.sub_category.name, 2), ('Hair styling', 1)])
        self.assertEqual(data['profileViews'], 42)
        self.assertNotIn('earn', str(data).lower())

    def test_date_range_filters_by_booking_date(self):
        self._booking(status='completed', start='09:00', end='10:00')
        self._booking(status='completed', day_offset=10, start='09:00', end='10:00')
        window_end = (self.date + timedelta(days=5)).strftime('%d-%m-%y')
        data = self.artist_client.get(self.url, {'from_date': self.date.strftime('%d-%m-%y'), 'to_date': window_end}).data['data']
        self.assertEqual(data['totalBookings'], 1)
        late = self.artist_client.get(self.url, {'from_date': (self.date + timedelta(days=6)).strftime('%d-%m-%y')}).data['data']
        self.assertEqual(late['totalBookings'], 1)
        self.assertEqual(self.artist_client.get(self.url, {'from_date': window_end, 'to_date': self.date.strftime('%d-%m-%y')}).status_code, 400)

    def test_only_own_data_and_empty_state(self):
        self._booking(status='completed')
        other, _, _ = make_artist(phone_number='+919000006011')
        data = other.get(self.url).data['data']
        self.assertEqual((data['totalBookings'], data['repeatClients'], data['topServices']), (0, 0, []))
        self.assertEqual(self.customer_client.get(self.url).status_code, 400)
        self.assertEqual(APIClient().get(self.url).status_code, 401)
