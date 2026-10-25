"""SQLite ignores row locks, so a race cannot be reproduced in the test suite; what can be pinned is that the code
asks the database for the locks that make the check-then-insert safe on PostgreSQL."""
from unittest.mock import patch

from django.db.models import Manager
from django.test import TestCase

from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models import Booking
from tests.test_customers import make_customer
from tests.test_user_abuse_scenarios import MarketplaceMixin


class SlotLockingTest(MarketplaceMixin, TestCase):

    def _models_locked_while_booking(self, phone):
        locked = []
        real = Manager.select_for_update

        def spy(manager, *args, **kwargs):
            locked.append(manager.model)
            return real(manager, *args, **kwargs)

        client, _ = make_customer(phone_number=phone)
        with patch.object(Manager, 'select_for_update', spy):
            self.assertEqual(self.book(client).status_code, 201)
        return locked

    def test_booking_a_slot_locks_the_artist_before_checking_for_clashes(self):
        locked = self._models_locked_while_booking('+919100001201')
        self.assertIn(ArtistProfile, locked, 'two requests for the same artist must queue behind a row lock, '
                                              'otherwise both can pass the clash check and both be saved')

    def test_the_days_existing_bookings_are_locked_too(self):
        locked = self._models_locked_while_booking('+919100001202')
        self.assertIn(Booking, locked)
        self.assertLess(locked.index(ArtistProfile), locked.index(Booking), 'artist first, then bookings: a fixed order avoids deadlocks')
