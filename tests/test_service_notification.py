"""Task 5 of the service-activation feature: telling customers a service is available.

Covers the trigger (only a real inactive -> active change, only after commit), the fan-out (customers only, each
person at most once per activation, failures isolated from the service's status), and the real FCM push."""
from datetime import timedelta
from unittest.mock import patch

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from firebase_admin import messaging

from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.core.tasks import notify_service_activated, redispatch_unnotified_service_activations
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationGateway, NotificationService

from tests.test_customers import make_artist, make_customer, make_user
from tests.test_help_center import make_admin

TASK_QUEUE = 'sunndari_apps.core.tasks.notify_service_activated.apply_async'
TYPE = 'service_activated'


class _Base(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Makeup')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Bridal Makeup', is_active=False)

    def activate(self, service=None):
        service = service or self.service
        service.is_active = True
        service.save()
        service.refresh_from_db()
        return service

    def iso(self, service=None):
        return (service or self.service).activated_at.isoformat()

    def refetch(self, service=None):
        return ServiceSubCategory.objects.get(pk=(service or self.service).pk)


# ─── The trigger ──────────────────────────────────────────────────────────────

class TriggerTest(_Base):

    def queued(self, action):
        with patch(TASK_QUEUE) as queue:
            with self.captureOnCommitCallbacks(execute=True):
                action()
        return queue

    def test_switching_a_service_on_queues_exactly_one_notification_job(self):
        queue = self.queued(self.activate)
        queue.assert_called_once()
        self.assertEqual(queue.call_args.kwargs['args'], [self.service.pk, self.refetch().activated_at.isoformat()])

    def test_a_service_created_active_is_announced_and_one_created_inactive_is_not(self):
        queue = self.queued(lambda: ServiceSubCategory.objects.create(category=self.category, name='Party Makeup'))
        queue.assert_called_once()
        quiet = self.queued(lambda: ServiceSubCategory.objects.create(category=self.category, name='HD Makeup', is_active=False))
        quiet.assert_not_called()

    def test_nothing_is_queued_for_an_already_active_service_a_deactivation_or_an_unrelated_edit(self):
        service = self.activate()
        def edit_and_resave():
            service.description = 'new wording'
            service.save()
            service.save()
        self.queued(edit_and_resave).assert_not_called()
        def deactivate():
            service.is_active = False
            service.save()
        self.queued(deactivate).assert_not_called()

    def test_switching_it_off_and_on_again_announces_it_again(self):
        service = self.activate()
        service.is_active = False
        service.save()
        queue = self.queued(lambda: self.activate(service))
        queue.assert_called_once()

    def test_a_rolled_back_save_announces_nothing(self):
        with patch(TASK_QUEUE) as queue:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        self.activate()
                        raise RuntimeError('something later in the request failed')
                except RuntimeError:
                    pass
        queue.assert_not_called()
        self.assertFalse(self.refetch().is_active)

    def test_a_broker_outage_never_breaks_or_undoes_the_activation(self):
        with patch(TASK_QUEUE, side_effect=ConnectionError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                self.activate()
        saved = self.refetch()
        self.assertTrue(saved.is_active)
        self.assertIsNotNone(saved.activated_at)
        self.assertIsNone(saved.activation_notified_at)             # so the redispatch job will pick it up

    def test_the_django_admin_checkbox_and_bulk_action_both_queue_it(self):
        admin = get_user_model().objects.create_superuser(username='boss', email='b@example.com', password='x')
        self.client.force_login(admin)
        with patch(TASK_QUEUE) as queue:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.service.pk]), {
                    'category': self.category.pk, 'name': 'Bridal Makeup', 'description': '', 'is_active': 'on'})
        self.assertEqual(queue.call_count, 1)
        other = ServiceSubCategory.objects.create(category=self.category, name='HD Makeup', is_active=False)
        with patch(TASK_QUEUE) as queue:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('admin:core_servicesubcategory_changelist'), {
                    'action': 'activate_selected', '_selected_action': [other.pk, self.service.pk]})
        self.assertEqual(queue.call_count, 1)                        # only `other` changed; the live one is left alone


# ─── The fan-out ──────────────────────────────────────────────────────────────

class _Fanout(_Base):

    def setUp(self):
        super().setUp()
        self.with_token, self.u1 = make_customer(phone_number='+919700000001')
        self.no_token, self.u2 = make_customer(phone_number='+919700000002')
        User.objects.filter(pk=self.u1.pk).update(fcm_token='token-1')
        self.inactive_customer = make_user('+919700000003', 'customer')
        User.objects.filter(pk=self.inactive_customer.pk).update(is_active=False)
        _, self.artist, _ = make_artist(phone_number='+919700000004')
        _, self.admin_user = make_admin(phone_number='+919700000005')
        for patcher in (
            patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'),
            patch('sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        send = patch('sunndari_apps.notifications.utils.messaging.send', return_value='projects/p/messages/1')
        self.fcm = send.start()
        self.addCleanup(send.stop)
        self.activate()

    def run_task(self, service=None):
        service = service or self.service
        return notify_service_activated(service.pk, self.refetch(service).activated_at.isoformat())

    def got(self, user):
        return Notification.objects.filter(user_id=user.user_id, type=TYPE)


class FanoutTest(_Fanout):

    def test_every_active_customer_and_nobody_else_is_told(self):
        result = self.run_task()
        self.assertEqual((result['sent'], result['failed']), (2, 0))
        self.assertEqual(self.got(self.u1).count(), 1)
        self.assertEqual(self.got(self.u2).count(), 1)
        for excluded in (self.inactive_customer, self.artist, self.admin_user):
            self.assertEqual(self.got(excluded).count(), 0, excluded.role)

    def test_the_notification_says_what_it_is_about(self):
        self.run_task()
        n = self.got(self.u1).get()
        self.assertEqual(n.title, 'New service available')
        self.assertIn('Bridal Makeup', n.message)
        self.assertIn('Makeup', n.message)
        self.assertEqual((n.reference_id, n.booking_id), (self.service.pk, None))

    def test_the_push_goes_to_the_device_token_with_a_payload_the_app_can_open(self):
        self.run_task()
        self.fcm.assert_called_once()
        sent = self.fcm.call_args.args[0]
        self.assertEqual(sent.token, 'token-1')
        self.assertEqual((sent.notification.title, 'Bridal Makeup' in sent.notification.body), ('New service available', True))
        n = self.got(self.u1).get()
        self.assertEqual(sent.data, {'type': TYPE, 'notificationId': str(n.notification_id), 'referenceId': str(self.service.pk)})
        n.refresh_from_db()
        self.assertEqual((n.delivery_status, n.fcm_message_id), ('sent', 'projects/p/messages/1'))

    def test_a_customer_with_no_device_still_gets_the_in_app_notification(self):
        self.run_task()
        n = self.got(self.u2).get()
        self.assertEqual((n.delivery_status, n.failure_reason), ('failed', 'No device token registered'))

    def test_the_firestore_feed_is_written_with_the_reference(self):
        self.run_task()
        mirror = NotificationService  # noqa: F841 (documenting the path)
        from sunndari_apps.notifications.utils import NotificationFirebaseUtils
        calls = NotificationFirebaseUtils.sync_notification.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c.kwargs['reference_id'] == self.service.pk and c.kwargs['type'] == TYPE for c in calls))

    def test_the_activation_is_marked_notified(self):
        self.assertIsNone(self.refetch().activation_notified_at)
        self.run_task()
        self.assertIsNotNone(self.refetch().activation_notified_at)


class IdempotencyTest(_Fanout):

    def test_running_the_job_again_sends_nothing_more(self):
        self.run_task()
        again = self.run_task()
        self.assertEqual(again['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 2)
        self.assertEqual(self.fcm.call_count, 1)

    def test_a_duplicate_job_that_arrives_while_the_first_is_running_does_nothing(self):
        claim = ServiceSubCategory.claim_activation_notification(self.service.pk, self.refetch().activated_at)
        self.assertIsNotNone(claim)                                      # job one has the activation
        self.assertEqual(self.run_task()['sent'], 0)                     # job two cannot take it
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_job_for_an_old_activation_does_nothing(self):
        stale = self.refetch().activated_at - timedelta(seconds=5)
        self.assertEqual(notify_service_activated(self.service.pk, stale.isoformat())['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_service_switched_off_before_the_job_runs_is_not_announced(self):
        stamp = self.refetch().activated_at.isoformat()
        self.service.is_active = False
        self.service.save()
        self.assertEqual(notify_service_activated(self.service.pk, stamp)['sent'], 0)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    def test_a_category_switched_off_before_the_job_runs_is_not_announced(self):
        self.category.is_active = False
        self.category.save()
        self.assertEqual(self.run_task()['sent'], 0)

    def test_a_new_activation_is_announced_again_to_everyone(self):
        self.run_task()
        self.service.is_active = False
        self.service.save()
        self.activate()
        self.assertEqual(self.run_task()['sent'], 2)
        self.assertEqual(self.got(self.u1).count(), 2)

    def test_a_customer_who_could_not_be_notified_is_retried_and_nobody_gets_two(self):
        real_notify = NotificationService.notify
        def flaky(user_id, **kwargs):
            return None if user_id == self.u2.user_id else real_notify(user_id=user_id, **kwargs)
        with patch.object(NotificationService, 'notify', side_effect=flaky):
            first = self.run_task()
        self.assertEqual((first['sent'], first['failed']), (1, 1))
        self.assertIsNone(self.refetch().activation_notified_at)         # claim handed back so the job can finish
        second = self.run_task()
        self.assertEqual((second['sent'], second['skipped']), (1, 1))
        self.assertEqual((self.got(self.u1).count(), self.got(self.u2).count()), (1, 1))

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
        self.assertIsNone(self.refetch().activation_notified_at)
        self.assertTrue(self.refetch().is_active)                         # the activation itself is untouched
        self.run_task()
        self.assertEqual((self.got(self.u1).count(), self.got(self.u2).count()), (1, 1))

    def test_a_push_failure_never_touches_the_service_or_stops_the_rest(self):
        self.fcm.side_effect = Exception('FCM is down')
        result = self.run_task()
        self.assertEqual(result['sent'], 2)                               # the in-app notification still exists
        self.assertTrue(self.refetch().is_active)
        self.assertEqual(self.got(self.u1).get().delivery_status, 'failed')


class RedispatchTest(_Base):

    def setUp(self):
        super().setUp()
        self.now = timezone.now()

    def make(self, name, minutes_ago, notified=False, active=True):
        service = ServiceSubCategory.objects.create(category=self.category, name=name)
        ServiceSubCategory.objects.filter(pk=service.pk).update(
            is_active=active, activated_at=self.now - timedelta(minutes=minutes_ago),
            activation_notified_at=self.now if notified else None)
        return service

    def test_only_recent_unsent_live_activations_are_queued_again(self):
        due = self.make('Due', minutes_ago=30)
        self.make('Still being sent', minutes_ago=1)
        self.make('Stale news', minutes_ago=60 * 30)
        self.make('Already sent', minutes_ago=30, notified=True)
        self.make('Switched off', minutes_ago=30, active=False)
        with patch('sunndari_apps.core.tasks.notify_service_activated.delay') as delay:
            self.assertEqual(redispatch_unnotified_service_activations(), 1)
        delay.assert_called_once_with(due.pk, ServiceSubCategory.objects.get(pk=due.pk).activated_at.isoformat())

    def test_it_is_scheduled(self):
        from django.conf import settings
        self.assertIn('sunndari_apps.core.tasks.redispatch_unnotified_service_activations',
                      [e['task'] for e in settings.CELERY_BEAT_SCHEDULE.values()])


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

    def test_the_notification_history_exposes_what_each_notification_is_about(self):
        self.run_task()
        rows = self.with_token.get('/notifications/get_all/').data['data']['data']
        item = next(r for r in rows if r['type'] == TYPE)
        self.assertEqual((item['referenceId'], item['bookingId']), (self.service.pk, None))
        single = self.with_token.get('/notifications/get/', {'notification_id': item['notificationId']})
        self.assertEqual(single.data['data']['referenceId'], self.service.pk)

    def test_other_notifications_keep_their_shape_with_no_reference(self):
        NotificationService.notify(user_id=self.u1.user_id, title='x', message='y', type='generic')
        row = next(r for r in self.with_token.get('/notifications/get_all/').data['data']['data'] if r['type'] == 'generic')
        self.assertIsNone(row['referenceId'])

    def test_reading_a_notification_does_not_change_whether_the_service_is_new(self):
        self.run_task()
        self.with_token.put('/notifications/mark_all_read/', {}, format='json')
        names = [r['name'] for r in self.with_token.get('/core/service-sub-category/recently_activated/').data['data']]
        self.assertEqual(names, ['Bridal Makeup'])
