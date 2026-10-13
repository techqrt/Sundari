from datetime import time

from django.test import TestCase

from sunndari_apps.artists.models import ArtistAvailabilityBlock
from sunndari_apps.customers.slot_rules import validate_slot

from tests.test_customers import make_artist, make_customer, make_schedule, next_weekday


class BlockTimeRangeTest(TestCase):
    add_url = '/artists/availability/block/add/'
    remove_url = '/artists/availability/block/remove/'
    get_all_url = '/artists/availability/block/get_all/'
    availability_url = '/customers/artists/availability/'

    def setUp(self):
        self.client, _, self.profile = make_artist(phone_number='+919000009100')
        self.customer_client, _ = make_customer(phone_number='+919000009101')
        self.day = next_weekday(2)
        make_schedule(self.profile, day_of_week=self.day.weekday(), start='09:00:00', end='20:00:00')
        self.date_str = self.day.strftime('%Y-%m-%d')

    def add(self, **extra):
        return self.client.post(self.add_url, {'block_date': self.date_str, **extra}, format='json')

    def blocks(self):
        return ArtistAvailabilityBlock.objects.filter(artist=self.profile, block_date=self.day)

    def slot_ok(self, start, end, **kwargs):
        try:
            validate_slot(self.profile.artist_id, self.day, time(*start), time(*end), **kwargs)
            return True
        except ValueError:
            return False

    # 1. optional start/end on add
    def test_add_without_times_still_blocks_the_whole_day(self):
        self.assertEqual(self.add(note='Holiday').status_code, 201)
        block = self.blocks().get()
        self.assertIsNone(block.start_time)
        self.assertIsNone(block.end_time)

    def test_add_with_times_blocks_only_those_hours(self):
        self.assertEqual(self.add(start_time='14:00:00', end_time='17:00:00').status_code, 201)
        block = self.blocks().get()
        self.assertEqual((str(block.start_time), str(block.end_time)), ('14:00:00', '17:00:00'))

    def test_times_must_come_as_a_valid_pair(self):
        for payload in ({'start_time': '14:00:00'}, {'end_time': '17:00:00'},
                        {'start_time': '17:00:00', 'end_time': '14:00:00'},
                        {'start_time': '14:00:00', 'end_time': '14:00:00'}):
            self.assertEqual(self.add(**payload).status_code, 400, payload)
        self.assertFalse(self.blocks().exists())

    # 3. several blocks on one date
    def test_several_blocks_on_one_date(self):
        self.assertEqual(self.add(start_time='11:00:00', end_time='13:00:00').status_code, 201)
        self.assertEqual(self.add(start_time='15:00:00', end_time='17:00:00').status_code, 201)
        self.assertEqual(self.blocks().count(), 2)

    def test_identical_block_is_still_idempotent(self):
        self.add(start_time='11:00:00', end_time='13:00:00')
        self.add(start_time='11:00:00', end_time='13:00:00')
        self.add()
        self.add()
        self.assertEqual(self.blocks().count(), 2)

    # 2. get_all returns date + times
    def test_get_all_returns_date_and_times_with_null_for_whole_day(self):
        self.add(start_time='11:00:00', end_time='13:00:00')
        self.add()
        rows = self.client.get(self.get_all_url).data['data']
        by_start = {r['startTime']: r for r in rows}
        self.assertEqual(by_start['11:00:00']['endTime'], '13:00:00')
        self.assertEqual(by_start['11:00:00']['blockDate'], self.date_str)
        self.assertIsNone(by_start[None]['endTime'])
        self.assertEqual(by_start[None]['blockDate'], self.date_str)

    # 4. remove deletes every block for the date
    def test_remove_clears_timed_and_whole_day_blocks_for_that_date_only(self):
        self.add(start_time='11:00:00', end_time='13:00:00')
        self.add(start_time='15:00:00', end_time='17:00:00')
        self.add()
        other = ArtistAvailabilityBlock.add(self.profile.artist_id, '2030-01-01', start_time='10:00:00', end_time='11:00:00')
        resp = self.client.delete(f'{self.remove_url}?block_date={self.date_str}')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.blocks().exists())
        self.assertTrue(ArtistAvailabilityBlock.objects.filter(block_id=other).exists())

    # 5. bookings skip blocked hours
    def test_blocked_hours_refuse_overlapping_slots_only(self):
        self.add(start_time='14:00:00', end_time='17:00:00')
        self.assertFalse(self.slot_ok((14, 0), (15, 0)))
        self.assertFalse(self.slot_ok((13, 0), (14, 30)))     # runs into the block
        self.assertFalse(self.slot_ok((16, 30), (18, 0)))
        self.assertTrue(self.slot_ok((12, 0), (14, 0)))       # ends exactly as the block starts
        self.assertTrue(self.slot_ok((17, 0), (18, 0)))       # starts exactly as it ends
        self.assertTrue(self.slot_ok((9, 0), (10, 0)))

    def test_every_block_of_the_day_is_honoured(self):
        self.add(start_time='11:00:00', end_time='13:00:00')
        self.add(start_time='15:00:00', end_time='17:00:00')
        self.assertFalse(self.slot_ok((12, 0), (13, 30)))
        self.assertTrue(self.slot_ok((13, 0), (15, 0)))
        self.assertFalse(self.slot_ok((16, 0), (17, 30)))

    def test_whole_day_block_refuses_every_slot(self):
        self.add()
        self.assertFalse(self.slot_ok((10, 0), (11, 0)))

    def test_travel_buffer_counts_towards_the_blocked_hours(self):
        self.add(start_time='14:00:00', end_time='17:00:00')
        self.assertTrue(self.slot_ok((17, 0), (18, 0)))
        self.assertFalse(self.slot_ok((17, 0), (18, 0), travel_before=30))   # leaves at 16:30
        self.assertFalse(self.slot_ok((12, 0), (13, 30), return_buffer=45))  # back at 14:15

    def test_availability_lists_blocked_hours_without_flagging_the_day(self):
        self.add(start_time='14:00:00', end_time='17:00:00')
        data = self.customer_client.get(self.availability_url, {
            'artist_id': self.profile.artist_id, 'booking_date': self.day.strftime('%d-%m-%y'),
        }).data['data']
        self.assertFalse(data['isBlocked'])
        self.assertIn({'startTime': time(14, 0), 'endTime': time(17, 0)}, data['blockedRanges'])

    def test_availability_flags_a_whole_day_block(self):
        self.add()
        data = self.customer_client.get(self.availability_url, {
            'artist_id': self.profile.artist_id, 'booking_date': self.day.strftime('%d-%m-%y'),
        }).data['data']
        self.assertTrue(data['isBlocked'])
