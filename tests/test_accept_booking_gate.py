"""An artist can accept a booking request only while they can take bookings: approved, not switched off by an admin,
registration payment settled (or exempt) and their own bookings switch ON. Only *accepting* is blocked: declining,
cancelling and every other step of a booking that already exists are untouched. And a voided registration payment
or a rejection switches bookings OFF, so paying again never switches them back on by itself."""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from sunndari.constants import Constants
from sunndari_apps.artists.models import ArtistProfile, ArtistRegistrationPayment
from sunndari_apps.artists.registration_payment_service import RegistrationPaymentService
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.customers.models import Booking
from tests.booking_address import address_for
from tests.booking_paid import pay_booking
from tests.test_admin_panel import make_admin_client
from tests.test_customers import (
    make_artist, make_customer, make_location_preference, make_location_type, make_package, make_schedule,
    next_weekday, seed_booking_statuses, seed_payment_statuses,
)

STATUS = '/artists/bookings/update_status/'
ADMIN_TOGGLE = '/admin-panel/artists/accepting_bookings/'
ARTIST_TOGGLE = '/artists/profile/accepting_bookings/'


class AcceptBookingGateTest(TestCase):

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.artist_client, self.user, self.profile = make_artist(phone_number='+919900020001')
        self.package = make_package(self.profile, price=1500)
        self.location = make_location_type('Studio')
        make_location_preference(self.profile, self.location)
        self.date = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.date.weekday())
        self.customer, _ = make_customer(phone_number='+919900020002')
        self.admin, _ = make_admin_client(phone_number='+919900020003')
        self.hour = 8

    # --- helpers
    def _paid_request(self):
        """A booking request the customer has paid for, waiting for the artist (the artist only sees paid ones)."""
        self.hour += 2
        resp = self.customer.post('/customers/bookings/create/', {
            **address_for(self.customer), 'artist_id': self.profile.artist_id, 'package_id': self.package.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.date.strftime('%d-%m-%y'), 'start_time': f'{self.hour:02d}:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        booking_id = resp.data['data']['booking_id']
        pay_booking(booking_id)
        return booking_id

    def _set(self, booking_id, status):
        return self.artist_client.put(STATUS, {'booking_id': booking_id, 'status': status}, format='json')

    def _booking_status(self, booking_id):
        return Booking.objects.get(booking_id=booking_id).status.name

    def _profile(self, **fields):
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(**fields)

    def _pay_registration(self, voided=False):
        from decimal import Decimal
        return ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=PaymentStatus.objects.get(name='paid'), paid_at=timezone.now(),
            refund_requested_at=timezone.now() if voided else None,
        )

    def _refused(self, booking_id, message):
        resp = self._set(booking_id, 'confirmed')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(message, resp.data['message'])
        self.assertEqual(self._booking_status(booking_id), 'pending')

    # --- accepting
    def test_a_live_artist_can_accept(self):
        booking_id = self._paid_request()
        self.assertEqual(self._set(booking_id, 'confirmed').status_code, 200)
        self.assertEqual(self._booking_status(booking_id), 'confirmed')

    def test_an_artist_with_bookings_off_cannot_accept_until_they_turn_them_on(self):
        booking_id = self._paid_request()
        self.assertEqual(self.artist_client.put(ARTIST_TOGGLE, {'is_accepting_bookings': False}, format='json').status_code, 200)
        self._refused(booking_id, Constants.accepting_off_cannot_confirm)
        self.assertEqual(self.artist_client.put(ARTIST_TOGGLE, {'is_accepting_bookings': True}, format='json').status_code, 200)
        self.assertEqual(self._set(booking_id, 'confirmed').status_code, 200)

    def test_an_admin_off_stops_accepting_and_the_artist_cannot_undo_it(self):
        booking_id = self._paid_request()
        self.assertEqual(self.admin.put(ADMIN_TOGGLE, {'artist_id': self.profile.artist_id, 'is_accepting_bookings': False}, format='json').status_code, 200)
        self._refused(booking_id, Constants.accepting_locked_by_admin)
        self.assertEqual(self.artist_client.put(ARTIST_TOGGLE, {'is_accepting_bookings': True}, format='json').status_code, 400)
        self._refused(booking_id, Constants.accepting_locked_by_admin)

    def test_an_artist_whose_registration_payment_is_not_settled_cannot_accept_even_if_the_switch_says_on(self):
        booking_id = self._paid_request()
        self._profile(registration_fee_exempt=False, is_accepting_bookings=True)          # no payment, not exempt
        self._refused(booking_id, Constants.accepting_requires_payment)

    def test_a_refunded_registration_payment_stops_accepting(self):
        self._profile(registration_fee_exempt=False)
        self._pay_registration()
        booking_id = self._paid_request()
        self.assertEqual(self._set(self._paid_request(), 'confirmed').status_code, 200)    # fine while paid
        ArtistRegistrationPayment.objects.filter(artist=self.profile).update(refund_requested_at=timezone.now())
        self._refused(booking_id, Constants.accepting_requires_payment)

    def test_an_artist_who_is_not_approved_or_is_suspended_cannot_accept(self):
        requests = [self._paid_request() for _ in range(3)]        # made while the artist is live
        for booking_id, (approval, message) in zip(requests, (
                ('pending', Constants.accepting_requires_approval),
                ('rejected', Constants.accepting_requires_approval),
                ('suspended', Constants.artist_suspended))):
            self._profile(approval_status=ApprovalStatus.objects.get(name=approval))
            self._refused(booking_id, message)

    # --- everything else about an existing booking is unaffected
    def test_existing_bookings_are_untouched_and_the_artist_can_still_decline_or_cancel(self):
        confirmed = self._paid_request()
        self.assertEqual(self._set(confirmed, 'confirmed').status_code, 200)
        waiting = self._paid_request()
        declined = self._paid_request()
        self._profile(is_accepting_bookings=False, accepting_locked_by_admin=True)
        self.assertEqual(self._booking_status(confirmed), 'confirmed')                     # still confirmed
        self.assertEqual(self._booking_status(waiting), 'pending')
        self.assertEqual(self._set(declined, 'cancelled').status_code, 200)               # may still decline a request
        self.assertEqual(self._booking_status(declined), 'cancelled')
        self.assertEqual(self._set(confirmed, 'cancelled').status_code, 200)              # and cancel a confirmed one
        self.assertEqual(self._booking_status(confirmed), 'cancelled')
        self._refused(waiting, Constants.accepting_locked_by_admin)                        # but not accept a new one

    def test_the_customer_still_sees_their_booking_when_the_artist_is_switched_off(self):
        booking_id = self._paid_request()
        self._profile(is_accepting_bookings=False)
        resp = self.customer.get('/customers/bookings/get/', {'booking_id': booking_id})
        self.assertEqual(resp.status_code, 200)

    def test_a_customer_cannot_use_the_artists_status_endpoint(self):
        booking_id = self._paid_request()
        resp = self.customer.put(STATUS, {'booking_id': booking_id, 'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._booking_status(booking_id), 'pending')


class BookingsOffOnRefundTest(TestCase):
    """A voided registration payment or a rejection switches bookings OFF; paying again does not switch them on."""

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        for name in ('pending', 'approved', 'rejected', 'suspended'):
            ApprovalStatus.objects.get_or_create(name=name, defaults={'description': name.title()})
        self.artist_client, self.user, self.profile = make_artist(phone_number='+919900021001')
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(registration_fee_exempt=False)

    def _paid(self):
        from decimal import Decimal
        return ArtistRegistrationPayment.objects.create(
            artist=self.profile, fee_amount=Decimal('1999.00'), payable_amount=Decimal('1999.00'),
            status=PaymentStatus.objects.get(name='paid'), paid_at=timezone.now(),
        )

    def _flag(self):
        return ArtistProfile.objects.get(artist_id=self.profile.artist_id).is_accepting_bookings

    def test_voiding_a_paid_registration_switches_bookings_off(self):
        self._paid()
        self.assertTrue(self._flag())
        RegistrationPaymentService.void_for_rejection(self.profile.artist_id)
        self.assertFalse(self._flag())
        self.assertFalse(ArtistProfile.is_eligible(self.profile.artist_id))

    def test_voiding_nothing_changes_nothing(self):
        self.assertIsNone(RegistrationPaymentService.void_for_rejection(self.profile.artist_id))
        self.assertTrue(self._flag())

    def test_rejecting_an_artist_switches_bookings_off(self):
        ArtistProfile.reject(artist_id=self.profile.artist_id, reason='incomplete')
        self.assertFalse(self._flag())

    def test_after_a_rejection_and_refund_paying_again_does_not_switch_bookings_on(self):
        self._paid()
        gateway = MagicMock()
        gateway.payment.refund.return_value = {'id': 'rfnd_1'}
        ArtistProfile.objects.filter(artist_id=self.profile.artist_id).update(submitted_for_review_at=timezone.now())
        admin, _ = make_admin_client(phone_number='+919900021002')
        payment = ArtistRegistrationPayment.objects.get(artist=self.profile)
        payment.gateway_payment_id = 'pay_1'
        payment.gateway = 'razorpay'
        payment.save()
        with patch('sunndari_apps.artists.registration_payment_service.RazorpayGateway.get_client', return_value=gateway):
            resp = admin.put('/admin-panel/artists/reject/', {'artist_id': self.profile.artist_id, 'reason': 'no'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(self._flag())
        self.assertFalse(ArtistProfile.is_eligible(self.profile.artist_id))
        # approved again and pays again: eligible, but still OFF until the artist chooses to switch on
        ArtistProfile.approve(artist_id=self.profile.artist_id)
        self._paid()
        self.assertTrue(ArtistProfile.is_eligible(self.profile.artist_id))
        self.assertFalse(self._flag())
        self.assertEqual(self.artist_client.put(ARTIST_TOGGLE, {'is_accepting_bookings': True}, format='json').status_code, 200)
        self.assertTrue(self._flag())
