"""Step 1 of the artist service announcement: the model's memory of an explicit announcement.

An announcement exists only because an admin asked for one. Creating, activating, deactivating or editing a service
never makes one, and a stale copy of a service can never erase one."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.core.models.service_sub_category import ANNOUNCEMENT_MESSAGE_MAX

FIELDS = ('artists_announced_at', 'artists_notified_at', 'artists_announcement_message')


class _Base(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Seasonal')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Diwali Special')

    def fresh(self, service=None):
        return ServiceSubCategory.objects.get(pk=(service or self.service).pk)

    def announce(self, message=None, service=None):
        return ServiceSubCategory.announce_to_artists((service or self.service).pk, message)


class AnnounceTest(_Base):

    def test_a_new_service_has_no_announcement(self):
        saved = self.fresh()
        self.assertEqual([getattr(saved, f) for f in FIELDS], [None, None, None])

    def test_announcing_records_the_time_and_the_standard_wording(self):
        before = timezone.now()
        stamp = self.announce()
        saved = self.fresh()
        self.assertTrue(before <= stamp <= timezone.now())
        self.assertEqual(saved.artists_announced_at, stamp)
        self.assertEqual(saved.artists_announcement_message, 'Diwali Special is now available. Add it to your services to start getting bookings.')
        self.assertIsNone(saved.artists_notified_at)

    def test_a_custom_message_is_kept_trimmed(self):
        self.announce('  Diwali is coming up! Add a Diwali Special service to your service list.  ')
        self.assertEqual(self.fresh().artists_announcement_message, 'Diwali is coming up! Add a Diwali Special service to your service list.')

    def test_a_blank_message_means_the_standard_wording(self):
        for blank in ('', '   ', None):
            self.announce(blank)
            self.assertIn('is now available', self.fresh().artists_announcement_message)

    def test_the_message_limit_is_enforced_and_changes_nothing(self):
        self.announce('first')
        with self.assertRaises(ValueError):
            self.announce('x' * (ANNOUNCEMENT_MESSAGE_MAX + 1))
        self.assertEqual(self.fresh().artists_announcement_message, 'first')
        self.announce('x' * ANNOUNCEMENT_MESSAGE_MAX)                                   # exactly the limit is fine

    def test_an_inactive_service_cannot_be_announced(self):
        self.service.is_active = False
        self.service.save()
        with self.assertRaises(ValueError) as raised:
            self.announce()
        self.assertEqual(str(raised.exception), 'Activate the service before notifying artists')
        self.assertEqual([getattr(self.fresh(), f) for f in FIELDS], [None, None, None])

    def test_a_service_under_an_inactive_category_cannot_be_announced(self):
        self.category.is_active = False
        self.category.save()
        with self.assertRaises(ValueError):
            self.announce()

    def test_an_unknown_service_is_refused(self):
        with self.assertRaises(ValueError):
            ServiceSubCategory.announce_to_artists(999999)

    def test_announcing_again_starts_a_fresh_announcement(self):
        first = self.announce('one')
        claim = ServiceSubCategory.claim_artist_announcement(self.service.pk, first)
        self.assertIsNotNone(claim)
        second = self.announce('two')
        saved = self.fresh()
        self.assertGreater(second, first)
        self.assertEqual((saved.artists_announced_at, saved.artists_announcement_message), (second, 'two'))
        self.assertIsNone(saved.artists_notified_at)                                      # a re-send can be claimed again

    def test_announcing_sends_nothing_by_itself(self):
        with patch('sunndari_apps.common.queueing.enqueue') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.announce()
        enqueue.assert_not_called()


class NothingButAnnounceCanSetItTest(_Base):

    def test_creating_activating_deactivating_and_editing_never_announce(self):
        service = ServiceSubCategory.objects.create(category=self.category, name='New Year', is_active=False)
        for step in ('activate', 'edit', 'deactivate', 'reactivate'):
            if step in ('activate', 'reactivate'):
                service.is_active = True
            elif step == 'deactivate':
                service.is_active = False
            else:
                service.description = 'edited'
            service.save()
            saved = ServiceSubCategory.objects.get(pk=service.pk)
            self.assertEqual([getattr(saved, f) for f in FIELDS], [None, None, None], step)

    def test_the_fields_cannot_be_set_through_a_form(self):
        from django import forms

        class Form(forms.ModelForm):
            class Meta:
                model = ServiceSubCategory
                fields = '__all__'
        for field in FIELDS:
            self.assertNotIn(field, Form().fields)

    def test_activating_deactivating_or_editing_leaves_an_existing_announcement_alone(self):
        stamp = self.announce('hello')
        before = [getattr(self.fresh(), f) for f in FIELDS]
        service = self.fresh()
        service.description = 'edited'
        service.save()
        service.is_active = False
        service.save()
        service.is_active = True
        service.save()
        self.assertEqual([getattr(self.fresh(), f) for f in FIELDS], before)

    def test_a_stale_copy_cannot_erase_an_announcement_or_its_claim(self):
        stale = self.fresh()                                                  # an admin opens the edit form ...
        stamp = self.announce('announced meanwhile')                          # ... another admin announces ...
        claim = ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp)   # ... and the job takes the claim
        stale.description = 'saved from the old form'
        stale.save()
        saved = self.fresh()
        self.assertEqual(saved.description, 'saved from the old form')
        self.assertEqual((saved.artists_announced_at, saved.artists_notified_at, saved.artists_announcement_message),
                         (stamp, claim, 'announced meanwhile'))

    def test_a_partial_save_does_not_touch_it(self):
        stamp = self.announce()
        service = self.fresh()
        service.name = 'Renamed'
        service.save(update_fields=['name'])
        self.assertEqual(self.fresh().artists_announced_at, stamp)


class ClaimTest(_Base):

    def test_exactly_one_claim_wins_per_announcement(self):
        stamp = self.announce()
        first = ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp)
        second = ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.fresh().artists_notified_at, first)

    def test_a_claim_for_an_old_announcement_loses(self):
        old = self.announce('old')
        self.announce('new')
        self.assertIsNone(ServiceSubCategory.claim_artist_announcement(self.service.pk, old))

    def test_nothing_can_be_claimed_without_an_announcement(self):
        self.assertIsNone(ServiceSubCategory.claim_artist_announcement(self.service.pk, timezone.now()))

    def test_a_service_switched_off_after_announcing_cannot_be_claimed(self):
        stamp = self.announce()
        self.service.is_active = False
        self.service.save()
        self.assertIsNone(ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp))
        self.assertIsNone(self.fresh().artists_notified_at)

    def test_a_category_switched_off_after_announcing_cannot_be_claimed(self):
        stamp = self.announce()
        self.category.is_active = False
        self.category.save()
        self.assertIsNone(ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp))

    def test_releasing_hands_back_only_the_callers_own_claim(self):
        stamp = self.announce()
        claim = ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp)
        other = claim + timedelta(seconds=1)                                                       # a claim that is not ours
        ServiceSubCategory.release_artist_announcement(self.service.pk, other)
        self.assertEqual(self.fresh().artists_notified_at, claim)                                   # untouched
        ServiceSubCategory.release_artist_announcement(self.service.pk, claim)
        self.assertIsNone(self.fresh().artists_notified_at)
        self.assertIsNotNone(ServiceSubCategory.claim_artist_announcement(self.service.pk, stamp))  # retry can take it again
