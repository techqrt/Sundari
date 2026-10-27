"""Step 3: the admin's way of telling artists about a service - the "Send notification to artists" tick on the edit form
(with an optional message), and the "Announce selected services to artists" bulk action - driven through the real
admin views. Activating and deactivating must never notify."""
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.core.tasks import notify_artists_service_announced
from sunndari_apps.notifications.models.notification import Notification

from django.test import TestCase
from tests.test_customers import make_artist, make_customer

QUEUE = 'sunndari_apps.core.tasks.notify_artists_service_announced.apply_async'
CHANGELIST = 'admin:core_servicesubcategory_changelist'


class AdminAnnounceTest(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Seasonal')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Diwali Special')
        self.staff = get_user_model().objects.create_superuser(username='ops', email='ops@example.com', password='x')
        self.client.force_login(self.staff)
        self.queue = []
        patcher = patch(QUEUE, side_effect=lambda *a, **kw: self.queue.append(tuple(kw['args'])))
        patcher.start()
        self.addCleanup(patcher.stop)

    def form(self, service=None, **extra):
        service = service or self.service
        data = {'category': service.category_id, 'name': service.name, 'description': '', **extra}
        if service.is_active and 'is_active' not in extra:
            data['is_active'] = 'on'
        return data

    def post(self, service=None, **extra):
        service = service or self.service
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('admin:core_servicesubcategory_change', args=[service.pk]), self.form(service, **extra))

    def fresh(self, service=None):
        return ServiceSubCategory.objects.get(pk=(service or self.service).pk)

    def bulk(self, action, ids=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse(CHANGELIST), {'action': action, '_selected_action': ids or [self.service.pk]}, follow=True)

    # ── the tick on the edit form ────────────────────────────────────────────

    def test_the_form_shows_the_tick_and_the_message_field_unticked(self):
        page = self.client.get(reverse('admin:core_servicesubcategory_change', args=[self.service.pk])).content.decode()
        self.assertIn('name="notify_artists"', page)
        self.assertIn('name="artists_message"', page)
        self.assertNotRegex(page, r'name="notify_artists"[^>]*checked')

    def test_ticking_it_announces_with_the_admins_wording_and_queues_one_job(self):
        response = self.post(notify_artists='on', artists_message='Diwali is coming up! Add a Diwali Special service to your service list.')
        self.assertEqual(response.status_code, 302)
        service = self.fresh()
        self.assertEqual(service.artists_announcement_message, 'Diwali is coming up! Add a Diwali Special service to your service list.')
        self.assertEqual(self.queue, [(service.pk, service.artists_announced_at.isoformat())])

    def test_a_blank_message_sends_the_standard_wording(self):
        self.post(notify_artists='on', artists_message='   ')
        self.assertEqual(self.fresh().artists_announcement_message,
                         'Diwali Special is now available. Add it to your services to start getting bookings.')

    def test_the_job_is_queued_only_once_the_save_has_committed(self):
        # a worker must never run before the announcement is visible in the database, so queuing waits for the commit
        self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.service.pk]), self.form(notify_artists='on'))
        self.assertEqual(self.queue, [])
        self.assertIsNotNone(self.fresh().artists_announced_at)

    def test_saving_without_the_tick_never_announces_even_with_a_message(self):
        self.post(artists_message='sneaky', description='edited')
        self.assertEqual((self.queue, self.fresh().artists_announced_at), ([], None))

    def test_switching_on_without_the_tick_never_announces(self):
        off = ServiceSubCategory.objects.create(category=self.category, name='Holi Special', is_active=False)
        self.post(off, is_active='on')
        self.assertTrue(self.fresh(off).is_active)
        self.assertEqual((self.queue, self.fresh(off).artists_announced_at), ([], None))

    def test_switching_on_and_ticking_in_one_save_announces(self):
        off = ServiceSubCategory.objects.create(category=self.category, name='Holi Special', is_active=False)
        self.post(off, is_active='on', notify_artists='on')
        self.assertEqual(len(self.queue), 1)
        self.assertTrue(self.fresh(off).is_active)

    def test_ticking_while_the_service_is_off_is_refused_and_saves_nothing(self):
        response = self.post(notify_artists='on', is_active='', description='changed')   # unticking Active in the same save
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activate the service before notifying artists')
        service = self.fresh()
        self.assertEqual((self.queue, service.artists_announced_at, service.description, service.is_active), ([], None, None, True))

    def test_ticking_while_the_category_is_off_is_refused(self):
        ServiceCategory.objects.filter(pk=self.category.pk).update(is_active=False)
        response = self.post(notify_artists='on')
        self.assertContains(response, 'Activate the service before notifying artists')
        self.assertEqual(self.queue, [])

    def test_a_message_over_the_limit_is_refused(self):
        response = self.post(notify_artists='on', artists_message='x' * 301)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((self.queue, self.fresh().artists_announced_at), ([], None))

    def test_the_tick_works_on_the_add_page_too(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('admin:core_servicesubcategory_add'), {
                'category': self.category.pk, 'name': 'New Year', 'description': '', 'is_active': 'on', 'notify_artists': 'on'})
        self.assertEqual(response.status_code, 302)
        created = ServiceSubCategory.objects.get(name='New Year')
        self.assertEqual(self.queue, [(created.pk, created.artists_announced_at.isoformat())])

    def test_the_tick_is_not_remembered_and_nothing_extra_is_stored(self):
        self.post(notify_artists='on')
        page = self.client.get(reverse('admin:core_servicesubcategory_change', args=[self.service.pk])).content.decode()
        self.assertNotRegex(page, r'name="notify_artists"[^>]*checked')
        self.assertFalse(hasattr(self.fresh(), 'notify_artists'))
        self.post(description='second save')                                        # saving again, untiked, sends nothing more
        self.assertEqual(len(self.queue), 1)

    def test_every_announcement_is_written_to_the_admin_history(self):
        self.post(notify_artists='on', artists_message='Hello artists')
        entry = LogEntry.objects.get(object_id=str(self.service.pk), change_message__contains='Announced to artists')
        self.assertEqual(entry.user_id, self.staff.pk)
        self.assertIn('Hello artists', entry.change_message)
        self.assertEqual(LogEntry.objects.filter(object_id=str(self.service.pk), change_message__contains='Announced to artists').count(), 1)

    def test_the_last_sent_time_is_shown_on_the_form_and_in_the_list(self):
        self.post(notify_artists='on')
        stamp = self.fresh().artists_announced_at
        self.assertIsNotNone(stamp)
        form = self.client.get(reverse('admin:core_servicesubcategory_change', args=[self.service.pk])).content.decode()
        self.assertIn('Artists announced at', form)
        self.assertIn('Artists announced at', self.client.get(reverse(CHANGELIST)).content.decode())

    def test_the_announcement_fields_cannot_be_posted_by_hand(self):
        self.post(artists_announced_at='2030-01-01 00:00:00', artists_notified_at='2030-01-01 00:00:00', artists_announcement_message='forged')
        service = self.fresh()
        self.assertEqual((service.artists_announced_at, service.artists_notified_at, service.artists_announcement_message), (None, None, None))

    def test_a_broker_outage_keeps_the_announcement_and_tells_the_admin(self):
        with patch(QUEUE, side_effect=ConnectionError('broker down')):
            response = self.post(notify_artists='on')
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.fresh().artists_announced_at)

    # ── the bulk action ──────────────────────────────────────────────────────

    def test_the_bulk_action_announces_every_live_service_and_reports_the_hidden_ones(self):
        live2 = ServiceSubCategory.objects.create(category=self.category, name='Karwa Chauth')
        hidden = ServiceSubCategory.objects.create(category=self.category, name='Hidden', is_active=False)
        response = self.bulk('announce_selected', [self.service.pk, live2.pk, hidden.pk])
        self.assertEqual(sorted(a[0] for a in self.queue), sorted([self.service.pk, live2.pk]))
        self.assertIsNone(self.fresh(hidden).artists_announced_at)
        self.assertContains(response, 'Hidden: Activate the service before notifying artists')
        self.assertEqual(self.fresh(live2).artists_announcement_message,
                         'Karwa Chauth is now available. Add it to your services to start getting bookings.')
        self.assertEqual(LogEntry.objects.filter(object_id=str(live2.pk), change_message__contains='Announced to artists').count(), 1)

    def test_the_bulk_action_needs_change_permission(self):
        viewer = get_user_model().objects.create_user(username='viewer', password='x', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_servicesubcategory'))
        self.client.force_login(viewer)
        self.bulk('announce_selected')
        self.assertEqual((self.queue, self.fresh().artists_announced_at), ([], None))

    def test_activating_and_deactivating_in_bulk_never_notify(self):
        self.bulk('deactivate_selected')
        self.bulk('activate_selected')
        self.bulk('activate_selected')
        self.assertEqual((self.queue, self.fresh().artists_announced_at), ([], None))
        self.assertEqual(Notification.objects.count(), 0)

    # ── end to end ───────────────────────────────────────────────────────────

    def test_ticking_the_box_reaches_the_approved_artists_through_the_worker(self):
        _, approved, _ = make_artist(phone_number='+919700000001')
        _, pending, _ = make_artist(phone_number='+919700000002', approved=False)
        _, customer = make_customer(phone_number='+919700000003')
        self.post(notify_artists='on', artists_message='Diwali is coming up!')
        with patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'), \
                patch('sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'):
            for args in self.queue:
                notify_artists_service_announced(*args)
        got = lambda u: Notification.objects.filter(user_id=u.user_id, type='service_activated')
        self.assertEqual(got(approved).get().message, 'Diwali is coming up!')
        self.assertEqual((got(pending).count(), got(customer).count()), (0, 0))
