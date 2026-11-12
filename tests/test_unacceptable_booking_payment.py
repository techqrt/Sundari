"""A customer must not be charged for a booking request the artist can no longer accept, and a missed booking must give
back everything it took.

Before this, payment could still be started for a pending request whose artist was switched off, locked, unpaid or
rejected. The artist could not accept it, so the money just sat there until the booking's own date passed. Now:
  * starting a payment for such a request is refused (solo and group), and the customer can cancel instead;
  * a payment already in progress when the artist went off is still settled, and refunded by the usual retry job if
    nobody acts;
  * when the sweep ends a missed booking, coins redeemed against it go back (the cash refund already did).
Confirmed bookings are never touched by any of this."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.customers.models import Booking
from sunndari_apps.customers.tasks import mark_missed_bookings
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.models import Payment, PaymentOrder
from sunndari_apps.wallet.models import CoinConfig, CustomerWallet, RedemptionTier
from tests.test_customers import make_artist, make_location_preference, make_package, make_schedule
from tests.test_e2e_artist_lifecycle import E2EBase


class UnacceptableBookingPaymentTest(E2EBase):

    def setUp(self):
        super().setUp()
        self.artist, self.user, self.profile = self._live_artist('+919234500601')
        self.pay_registration(self.artist)
        self.assertEqual(self.artist_switch(self.artist, True).status_code, 200)

    def _init(self, booking_id):
        return self.customer.post('/customers/payments/initiate/', {'booking_id': booking_id}, format='json')

    def _assert_unpayable(self, booking_id):
        orders_before = self.gw.order.create.call_count
        resp = self._init(booking_id)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn(Constants.payment_artist_cannot_accept, resp.data['message'])
        self.assertEqual(Payment.objects.filter(booking_id=booking_id).count(), 0, 'no payment row may be created')
        self.assertEqual(self.gw.order.create.call_count, orders_before, 'no gateway order may be created')

    # --- B: payment is refused
    def test_a_live_artists_request_can_still_be_paid(self):
        booking = self.book(self.profile)
        self.assertIn(self._init(booking).status_code, (200, 201))

    def test_payment_is_refused_for_every_reason_the_artist_cannot_accept(self):
        bookings = [self.book(self.profile) for _ in range(4)]
        # 1. the artist's own switch is off
        self.assertEqual(self.artist_switch(self.artist, False).status_code, 200)
        self._assert_unpayable(bookings[0])
        self.assertEqual(self.artist_switch(self.artist, True).status_code, 200)
        # 2. an admin switched the artist off
        self.assertEqual(self.admin_switch(self.profile, False).status_code, 200)
        self._assert_unpayable(bookings[1])
        self.assertEqual(self.admin_switch(self.profile, True).status_code, 200)
        # 3. the registration payment was refunded
        ArtistRegistrationPayment.objects.filter(artist=self.profile).update(refund_requested_at=timezone.now())
        self._assert_unpayable(bookings[2])
        ArtistRegistrationPayment.objects.filter(artist=self.profile).update(refund_requested_at=None)
        # 4. the artist is no longer approved
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(approval_status=ApprovalStatus.objects.get(name='rejected'))
        self._assert_unpayable(bookings[3])
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(approval_status=ApprovalStatus.objects.get(name='approved'))
        # and with everything restored the same requests can be paid again
        self.assertIn(self._init(bookings[0]).status_code, (200, 201))

    def test_the_customer_can_cancel_the_unpayable_request_and_owes_nothing(self):
        booking = self.book(self.profile)
        self.admin_switch(self.profile, False)
        self._assert_unpayable(booking)
        cancel = self.customer.put('/customers/bookings/cancel/', {'booking_id': booking}, format='json')
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(self.booking_status(booking), 'cancelled')
        self.assertEqual(Payment.objects.filter(booking_id=booking).count(), 0)
        self.assertEqual(self.gw.refunds, [])

    def test_a_payment_already_in_progress_is_still_settled_and_is_refunded_if_nobody_acts(self):
        booking = self.book(self.profile)
        init = self._init(booking)                                     # checkout opened while the artist was live
        order_id = init.data['data']['gateway_order_id']
        self.admin_switch(self.profile, False)                          # ... then the artist is switched off
        payment_id = self.gw.pay(order_id)
        verify = self.customer.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(verify.status_code, 200, 'money the gateway captured is never dropped')
        self.assertEqual(Payment.objects.get(booking_id=booking).status.name, 'paid')
        self.assertEqual(self.artist_sets(self.artist, booking, 'confirmed').status_code, 400)
        Booking.objects.filter(booking_id=booking).update(booking_date=timezone.now().date() - timedelta(days=2))
        mark_missed_bookings()
        self.assertEqual(self.booking_status(booking), 'no_show')
        Payment.retry_owed_refunds()
        self.assertEqual(Payment.objects.get(booking_id=booking).status.name, 'refunded')
        self.assertEqual(len(self.gw.refunds), 1)
        self.assertEqual(Notification.objects.filter(user_id=self.customer_user.user_id, type='refund_initiated').count(), 1)

    def test_a_confirmed_booking_is_never_affected(self):
        booking = self.book(self.profile)
        self.pay_booking(booking)
        self.assertEqual(self.artist_sets(self.artist, booking, 'confirmed').status_code, 200)
        self.admin_switch(self.profile, False)
        resp = self._init(booking)
        self.assertNotIn(Constants.payment_artist_cannot_accept, resp.data['message'])
        self.assertEqual(self.booking_status(booking), 'confirmed')

    def test_a_group_payment_is_refused_if_any_booking_cannot_be_accepted(self):
        other = self._second_live_artist()
        blocked, healthy = self.book(self.profile), self._book_other(other)
        self.admin_switch(self.profile, False)
        resp = self.customer.post('/customers/payments/initiate_group/', {'booking_ids': [healthy, blocked]}, format='json')
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn(f'Booking #{blocked}', resp.data['message'])
        self.assertIn(Constants.payment_artist_cannot_accept, resp.data['message'])
        self.assertEqual(PaymentOrder.objects.count(), 0)
        self.assertEqual(Payment.objects.filter(booking_id__in=[healthy, blocked]).count(), 0)

    def test_a_group_payment_of_bookable_artists_still_works(self):
        other = self._second_live_artist()
        first, second = self.book(self.profile), self._book_other(other)
        resp = self.customer.post('/customers/payments/initiate_group/', {'booking_ids': [first, second]}, format='json')
        self.assertIn(resp.status_code, (200, 201), resp.data)

    # --- helpers for the group case
    def _second_live_artist(self):
        from sunndari_apps.core.models.location_type import LocationType
        _, _, other = make_artist(phone_number='+919234500602', name='Second Artist')
        make_package(other, price=1000, name='Second Package')
        make_location_preference(other, LocationType.objects.first())
        make_schedule(other, day_of_week=self.date.weekday())
        return other

    def _book_other(self, other):
        from sunndari_apps.artists.models import PricingPackage
        from sunndari_apps.core.models.location_type import LocationType
        from tests.booking_address import address_for
        self.hour += 2
        resp = self.customer.post('/customers/bookings/create/', {
            **address_for(self.customer), 'artist_id': other.artist_id,
            'package_id': PricingPackage.objects.filter(artist_id=other.artist_id).first().package_id,
            'location_type_id': LocationType.objects.first().location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': f'{self.hour:02d}:00:00'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data['data']['booking_id']


class MissedBookingGivesEverythingBackTest(E2EBase):
    """The sweep marks a booking missed once its time has passed; the retry job returns the cash; the coins must go
    back too, as they do on every cancellation path."""

    def setUp(self):
        super().setUp()
        self.artist, self.user, self.profile = self._live_artist('+919234500701')
        self.pay_registration(self.artist)
        self.artist_switch(self.artist, True)
        CoinConfig.objects.get_or_create(defaults={'coin_value_rupees': Decimal('0.01')})
        self.tier = RedemptionTier.objects.create(rupee_value=Decimal('100.00'))        # 10,000 coins
        CustomerWallet.credit(customer_id=self.customer_user.user_id, coins=10000, transaction_type='ADJUSTMENT')

    def _coins(self):
        return CustomerWallet.objects.get(customer_id=self.customer_user.user_id).balance_coins

    def _pay_with_coins(self, booking):
        init = self.customer.post('/customers/payments/initiate/', {'booking_id': booking, 'redemption_tier_id': self.tier.tier_id}, format='json')
        self.assertEqual(init.status_code, 201, init.data)
        order_id = init.data['data']['gateway_order_id']
        payment_id = self.gw.pay(order_id)
        verify = self.customer.post('/customers/payments/verify/', {
            'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': 'sig'}, format='json')
        self.assertEqual(verify.status_code, 200, verify.data)

    def _miss(self, booking):
        Booking.objects.filter(booking_id=booking).update(booking_date=timezone.now().date() - timedelta(days=2))
        return mark_missed_bookings()

    def test_coins_come_back_with_the_cash_when_a_request_is_never_accepted(self):
        booking = self.book(self.profile)
        self._pay_with_coins(booking)
        self.assertEqual(self._coins(), 0)                                           # redeemed
        self.assertEqual(self._miss(booking), 1)
        self.assertEqual(self.booking_status(booking), 'no_show')
        self.assertEqual(self._coins(), 10000)                                       # returned at once
        Payment.retry_owed_refunds()
        self.assertEqual(Payment.objects.get(booking_id=booking).status.name, 'refunded')
        self.assertEqual(len(self.gw.refunds), 1)

    def test_running_the_sweep_and_the_retry_job_again_changes_nothing(self):
        booking = self.book(self.profile)
        self._pay_with_coins(booking)
        self._miss(booking)
        Payment.retry_owed_refunds()
        self.assertEqual(mark_missed_bookings(), 0)
        Payment.retry_owed_refunds()
        self.assertEqual((self._coins(), len(self.gw.refunds)), (10000, 1), 'neither coins nor cash may be returned twice')

    def test_a_missed_confirmed_booking_also_returns_its_coins(self):
        booking = self.book(self.profile)
        self._pay_with_coins(booking)
        self.assertEqual(self.artist_sets(self.artist, booking, 'confirmed').status_code, 200)
        self._miss(booking)
        self.assertEqual(self._coins(), 10000)

    def test_a_missed_booking_without_coins_is_unaffected(self):
        booking = self.book(self.profile)
        self.pay_booking(booking)
        self._miss(booking)
        self.assertEqual(self._coins(), 10000)                                       # untouched wallet
        Payment.retry_owed_refunds()
        self.assertEqual(Payment.objects.get(booking_id=booking).status.name, 'refunded')
