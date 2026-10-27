"""Step 2 of the artist service announcement: telling artists a service is open for them to add.

The notification is sent only because an admin asked for it, only to approved and active artists, at most once per
person per announcement, and it never adds the service to anyone: that stays the artist's own choice."""
from datetime import timedelta
from unittest.mock import patch

from celery.exceptions import Retry
from django.test import TestCase
from django.utils import timezone
from firebase_admin import messaging

from sunndari_apps.artists.models import ArtistServiceOffering, PricingPackage
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ApprovalStatus, ServiceCategory, ServiceSubCategory
from sunndari_apps.core.tasks import notify_artists_service_announced, redispatch_unnotified_artist_announcements
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationGateway, NotificationService

from tests.test_customers import make_artist, make_customer, make_user
from tests.test_help_center import make_admin

TYPE = 'service_activated'
MESSAGE = 'Diwali is coming up! Add a Diwali Special service to your service list.'


class _Base(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Seasonal')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Diwali Special')

    def announce(self, message=MESSAGE, service=None):
        return ServiceSubCategory.announce_to_artists((service or self.service).pk, message)

    def refetch(self, service=None):
        return ServiceSubCategory.objects.get(pk=(service or self.service).pk)


# ─── Nothing notifies by itself ───────────────────────────────────────────────

class NothingNotifiesByItselfTest(_Base):

    def queued(self, action):
        with patch('sunndari_apps.common.queueing.enqueue') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                action()
        return enqueue

    def test_creating_activating_deactivating_and_editing_a_service_queue_nothing(self):
        def lifecycle():
            service = ServiceSubCategory.objects.create(category=self.category, name='New Year', is_active=False)
            service.is_active = True
            service.save()
            service.description = 'edited'
            service.save()
            service.is_active = False
            service.save()
            service.is_active = True
            service.save()
        self.queued(lifecycle).assert_not_called()

    def test_only_the_explicit_dispatch_queues_the_job_with_the_announcement_it_belongs_to(self):
        stamp = self.announce()
        with patch('sunndari_apps.core.tasks.notify_artists_service_announced.apply_async') as queue:
            queued = ServiceSubCategory.dispatch_artist_announcement(self.service.pk, stamp)
        self.assertTrue(queued)
        queue.assert_called_once()
        self.assertEqual(queue.call_args.kwargs['args'], [self.service.pk, stamp.isoformat()])

    def test_a_dead_job_queue_is_reported_not_raised(self):
        stamp = self.announce()
        with patch('sunndari_apps.core.tasks.notify_artists_service_announced.apply_async', side_effect=ConnectionError('broker down')):
            self.assertFalse(ServiceSubCategory.dispatch_artist_announcement(self.service.pk, stamp))
        self.assertIsNotNone(self.refetch().artists_announced_at)                       # the announcement itself stands


# ─── The fan-out ──────────────────────────────────────────────────────────────

class _Fanout(_Base):

    def setUp(self):
        super().setUp()
        self.approved_with_token = self._artist('+919810000001', approved=True, token='token-1')
        self.approved_no_token = self._artist('+919810000002', approved=True)
        self.pending = self._artist('+919810000003', approved=False)
        self.rejected = self._artist('+919810000004', approved=True)
        rejected, _ = ApprovalStatus.objects.get_or_create(name='rejected', defaults={'description': 'Rejected'})
        self.rejected[2].approval_status = rejected
        self.rejected[2].save()
        self.deactivated = self._artist('+919810000005', approved=True)
        User.objects.filter(pk=self.deactivated[1].pk).update(is_active=False)
        self.customer_client, self.customer = make_customer(phone_number='+919810000006')
        User.objects.filter(pk=self.customer.pk).update(fcm_token='customer-token')
        _, self.admin_user = make_admin(phone_number='+919810000007')
        for patcher in (
            patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'),
            patch('sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        send = patch('sunndari_apps.notifications.utils.messaging.send', return_value='projects/p/messages/1')
        self.fcm = send.start()
        self.addCleanup(send.stop)
        self.stamp = self.announce()

    def _artist(self, phone, approved, token=None):
        client, user, profile = make_artist(phone_number=phone, approved=approved)
        if token:
            User.objects.filter(pk=user.pk).update(fcm_token=token)
        return client, user, profile

    def run_task(self, service=None, stamp=None):
        service = service or self.service
        return notify_artists_service_announced(service.pk, (stamp or self.refetch(service).artists_announced_at).isoformat())

    def got(self, user):
        return Notification.objects.filter(user_id=user.user_id, type=TYPE)


class FanoutTest(_Fanout):

    def test_only_approved_active_artists_are_told(self):
        result = self.run_task()
        self.assertEqual((result['sent'], result['failed']), (2, 0))
        for told in (self.approved_with_token, self.approved_no_token):
            self.assertEqual(self.got(told[1]).count(), 1)
        for left_out in (self.pending, self.rejected, self.deactivated):
            self.assertEqual(self.got(left_out[1]).count(), 0)
        for not_an_artist in (self.customer, self.admin_user):
            self.assertEqual(self.got(not_an_artist).count(), 0, not_an_artist.role)

    def test_an_account_that_is_no_longer_an_artist_is_not_told_even_with_an_approved_profile(self):
        User.objects.filter(pk=self.approved_no_token[1].pk).update(role='customer')
        self.assertEqual(self.run_task()['sent'], 1)
        self.assertEqual(self.got(self.approved_no_token[1]).count(), 0)

    def test_the_artist_reads_the_admins_wording_and_gets_the_service_id_to_open(self):
        self.run_task()
        n = self.got(self.approved_with_token[1]).get()
        self.assertEqual(n.title, 'New service: Diwali Special')
        self.assertEqual(n.message, MESSAGE)
        self.assertEqual((n.reference_id, n.booking_id), (self.service.pk, None))

    def test_the_standard_wording_is_used_when_the_admin_wrote_none(self):
        self.stamp = self.announce(message='')
        self.run_task()
        self.assertEqual(self.got(self.approved_with_token[1]).get().message,
                         'Diwali Special is now available. Add it to your services to start getting bookings.')

    def test_the_push_goes_to_the_artists_device_with_what_the_app_needs_to_open_the_screen(self):
        self.run_task()
        self.fcm.assert_called_once()                                    # only the artist who has a device
        sent = self.fcm.call_args.args[0]
        n = self.got(self.approved_with_token[1]).get()
        self.assertEqual(sent.token, 'token-1')
        self.assertEqual((sent.notification.title, sent.notification.body), ('New service: Diwali Special', MESSAGE))
        self.assertEqual(sent.data, {'type': TYPE, 'notificationId': str(n.notification_id), 'referenceId': str(self.service.pk)})
        n.refresh_from_db()
        self.assertEqual((n.delivery_status, n.fcm_message_id), ('sent', 'projects/p/messages/1'))

    def test_an_artist_with_no_device_still_gets_it_in_the_app(self):
        self.run_task()
        n = self.got(self.approved_no_token[1]).get()
        self.assertEqual((n.delivery_status, n.failure_reason), ('failed', 'No device token registered'))

    def test_the_feed_is_written_with_the_service_reference(self):
        self.run_task()
        from sunndari_apps.notifications.utils import NotificationFirebaseUtils
        calls = NotificationFirebaseUtils.sync_notification.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c.kwargs['reference_id'] == self.service.pk and c.kwargs['type'] == TYPE for c in calls))

    def test_the_announcement_is_marked_notified(self):
        self.assertIsNone(self.refetch().artists_notified_at)
        self.run_task()
        self.assertIsNotNone(self.refetch().artists_notified_at)

    def test_notifying_never_adds_the_service_to_anyone(self):
        self.run_task()
        self.assertEqual(ArtistServiceOffering.objects.count(), 0)
        self.assertEqual(PricingPackage.objects.count(), 0)

    def test_nothing_is_emailed(self):
        from django.core import mail
        User.objects.filter(pk=self.approved_with_token[1].pk).update(email='artist@example.com')
        with patch('sunndari_apps.common.queueing.enqueue') as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                self.run_task()
        enqueue.assert_not_called()
        self.assertEqual(mail.outbox, [])


class IdempotencyTest(_Fanout):

    def test_running_the_job_again_sends_nothing_more(self):
        self.run_task()
        again = self.run_task()
        self.assertEqual(again['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 2)
        self.assertEqual(self.fcm.call_count, 1)

    def test_a_duplicate_job_that_arrives_while_the_first_is_running_does_nothing(self):
        claim = ServiceSubCategory.claim_artist_announcement(self.service.pk, self.refetch().artists_announced_at)
        self.assertIsNotNone(claim)
        self.assertEqual(self.run_task()['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_job_for_an_old_announcement_does_nothing(self):
        self.announce('a newer announcement')
        self.assertEqual(self.run_task(stamp=self.stamp)['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_service_switched_off_before_the_job_runs_is_not_announced(self):
        self.service.is_active = False
        self.service.save()
        self.assertEqual(self.run_task(stamp=self.stamp)['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_category_switched_off_before_the_job_runs_is_not_announced(self):
        self.category.is_active = False
        self.category.save()
        self.assertEqual(self.run_task(stamp=self.stamp)['sent'], 0)

    def test_announcing_again_tells_everyone_again_with_the_new_wording(self):
        self.run_task()
        self.stamp = self.announce('Wedding season is here! Add Bridal Glam to your services.')
        self.assertEqual(self.run_task()['sent'], 2)
        messages = sorted(self.got(self.approved_with_token[1]).values_list('message', flat=True))
        self.assertEqual(messages, sorted([MESSAGE, 'Wedding season is here! Add Bridal Glam to your services.']))

    def test_an_artist_who_could_not_be_notified_is_retried_and_nobody_gets_two(self):
        real_notify = NotificationService.notify
        failing = self.approved_no_token[1].user_id

        def flaky(user_id, **kwargs):
            return None if user_id == failing else real_notify(user_id=user_id, **kwargs)
        with patch.object(NotificationService, 'notify', side_effect=flaky):
            first = self.run_task()
        self.assertEqual((first['sent'], first['failed']), (1, 1))
        self.assertIsNone(self.refetch().artists_notified_at)             # claim handed back so the job can finish
        second = self.run_task()
        self.assertEqual((second['sent'], second['skipped']), (1, 1))
        self.assertEqual((self.got(self.approved_with_token[1]).count(), self.got(self.approved_no_token[1]).count()), (1, 1))

    def test_a_crash_midway_is_retried_without_repeating_anyone(self):
        calls = {'n': 0}
        real = Notification.exists_for_reference

        def explode_on_second(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2:
                raise RuntimeError('database went away')
            return real(*args, **kwargs)
        with patch.object(Notification, 'exists_for_reference', side_effect=explode_on_second):
            with self.assertRaises((RuntimeError, Retry)):
                self.run_task()
        self.assertIsNone(self.refetch().artists_notified_at)
        self.assertTrue(self.refetch().is_active)
        self.run_task()
        self.assertEqual((self.got(self.approved_with_token[1]).count(), self.got(self.approved_no_token[1]).count()), (1, 1))

    def test_a_push_failure_never_touches_the_service_or_stops_the_rest(self):
        self.fcm.side_effect = Exception('FCM is down')
        result = self.run_task()
        self.assertEqual(result['sent'], 2)                                # the in-app notification still exists
        self.assertTrue(self.refetch().is_active)
        self.assertEqual(self.got(self.approved_with_token[1]).get().delivery_status, 'failed')


class RedispatchTest(_Base):

    def make(self, name, minutes_ago, notified=False, active=True):
        service = ServiceSubCategory.objects.create(category=self.category, name=name)
        stamp = timezone.now() - timedelta(minutes=minutes_ago)
        ServiceSubCategory.objects.filter(pk=service.pk).update(
            is_active=active, artists_announced_at=stamp, artists_announcement_message='m',
            artists_notified_at=timezone.now() if notified else None)
        return service

    def test_only_recent_unsent_live_announcements_are_queued_again(self):
        due = self.make('Due', minutes_ago=30)
        self.make('Still being sent', minutes_ago=1)
        self.make('Stale news', minutes_ago=60 * 30)
        self.make('Already sent', minutes_ago=30, notified=True)
        self.make('Switched off', minutes_ago=30, active=False)
        ServiceSubCategory.objects.create(category=self.category, name='Never announced')
        with patch('sunndari_apps.core.tasks.notify_artists_service_announced.delay') as delay:
            self.assertEqual(redispatch_unnotified_artist_announcements(), 1)
        delay.assert_called_once_with(due.pk, ServiceSubCategory.objects.get(pk=due.pk).artists_announced_at.isoformat())

    def test_it_is_scheduled_and_the_customer_one_is_gone(self):
        from django.conf import settings
        tasks = [e['task'] for e in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertIn('sunndari_apps.core.tasks.redispatch_unnotified_artist_announcements', tasks)
        self.assertFalse([t for t in tasks if 'redispatch_unnotified_service_activations' in t])


# ─── The real FCM gateway ─────────────────────────────────────────────────────

class GatewayTest(TestCase):

    def setUp(self):
        self.user = make_user('+919700000010', 'customer')
        User.objects.filter(pk=self.user.pk).update(fcm_token='device-token')
        for target in ('sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized',):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)

    def send(self, **kwargs):
        return NotificationGateway.send(user_id=self.user.user_id, title='T', message='M', **kwargs)

    def test_a_push_is_sent_to_the_users_token(self):
        with patch('sunndari_apps.notifications.utils.messaging.send', return_value='msg-1') as send:
            result = self.send(data={'type': 'x', 'bookingId': 7, 'referenceId': None})
        message = send.call_args.args[0]
        self.assertEqual((message.token, message.notification.title, message.notification.body), ('device-token', 'T', 'M'))
        self.assertEqual(message.data, {'type': 'x', 'bookingId': '7'})                  # strings only; None left out
        self.assertEqual(result, {'success': True, 'message_id': 'msg-1', 'reason': None})

    def test_a_user_with_no_token_is_a_reported_failure_not_an_error(self):
        User.objects.filter(pk=self.user.pk).update(fcm_token=None)
        with patch('sunndari_apps.notifications.utils.messaging.send') as send:
            result = self.send()
        send.assert_not_called()
        self.assertEqual((result['success'], result['reason']), (False, 'No device token registered'))

    def test_a_dead_token_is_removed_so_it_is_not_tried_again(self):
        with patch('sunndari_apps.notifications.utils.messaging.send', side_effect=messaging.UnregisteredError('gone')):
            result = self.send()
        self.assertFalse(result['success'])
        self.assertIsNone(User.objects.get(pk=self.user.pk).fcm_token)

    def test_any_other_push_failure_is_reported_and_keeps_the_token(self):
        with patch('sunndari_apps.notifications.utils.messaging.send', side_effect=Exception('quota exceeded')):
            result = self.send()
        self.assertEqual((result['success'], result['reason']), (False, 'quota exceeded'))
        self.assertEqual(User.objects.get(pk=self.user.pk).fcm_token, 'device-token')

    def test_every_notification_in_the_app_now_goes_out_as_a_push_and_is_recorded(self):
        with patch('sunndari_apps.notifications.utils.messaging.send', return_value='msg-9'), \
                patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'):
            notification_id = NotificationService.notify(user_id=self.user.user_id, title='Hello', message='there')
        row = Notification.objects.get(pk=notification_id)
        self.assertEqual((row.delivery_status, row.fcm_message_id), ('sent', 'msg-9'))


# ─── What the API shows ───────────────────────────────────────────────────────

class ApiTest(_Fanout):

    def test_the_artist_sees_the_announcement_in_their_notifications_with_the_service_id(self):
        self.run_task()
        rows = self.approved_with_token[0].get('/notifications/get_all/').data['data']['data']
        item = next(r for r in rows if r['type'] == TYPE)
        self.assertEqual((item['referenceId'], item['bookingId'], item['message']), (self.service.pk, None, MESSAGE))
        single = self.approved_with_token[0].get('/notifications/get/', {'notification_id': item['notificationId']})
        self.assertEqual(single.data['data']['referenceId'], self.service.pk)

    def test_customers_see_nothing_about_it(self):
        self.run_task()
        rows = self.customer_client.get('/notifications/get_all/').data['data']['data']
        self.assertEqual([r for r in rows if r['type'] == TYPE], [])

    def test_other_notifications_keep_their_shape_with_no_reference(self):
        NotificationService.notify(user_id=self.approved_with_token[1].user_id, title='x', message='y', type='generic')
        row = next(r for r in self.approved_with_token[0].get('/notifications/get_all/').data['data']['data'] if r['type'] == 'generic')
        self.assertIsNone(row['referenceId'])
