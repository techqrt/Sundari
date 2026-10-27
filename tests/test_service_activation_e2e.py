"""The acceptance checklist of the artist service announcement (so far: activation + the notification job), walked as
one story through the real entry points: the Django admin form, the explicit announcement and its queued job, and the
artist / customer APIs. The admin checkbox, the artist popup and the customer visibility rule have their own steps."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from sunndari_apps.artists.models import ArtistServiceOffering
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ServiceSubCategory
from sunndari_apps.core.tasks import notify_artists_service_announced
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import make_artist, make_package
from tests.test_service_inactive_rules import _Fixture

QUEUE = 'sunndari_apps.core.tasks.notify_artists_service_announced.apply_async'
FCM = 'sunndari_apps.notifications.utils.messaging.send'
TYPE = 'service_activated'
WORDING = 'Diwali is coming up! Add a Diwali Special service to your service list.'


class AcceptanceFlowTest(_Fixture):
    """A brand-new service ('Diwali Special') that starts switched off."""

    def setUp(self):
        super().setUp()
        self.diwali = ServiceSubCategory.objects.create(category=self.makeup, name='Diwali Special', is_active=False)
        self.diwali_pkg = make_package(self.profile, sub_category=self.diwali, price=2200, name='Diwali Package')
        User.objects.filter(pk=self.artist_user.pk).update(fcm_token='artist-device')
        User.objects.filter(pk=self.customer.pk).update(fcm_token='customer-device')
        self.other_client, self.other_user, self.other_profile = make_artist(phone_number='+919800000010', name='Second Artist')
        self.new_client, self.new_user, self.new_profile = make_artist(phone_number='+919800000011', name='Not Yet Approved', approved=False)
        self.staff = get_user_model().objects.create_superuser(username='ops', email='ops@example.com', password='x')
        for target in ('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification',
                       'sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        fcm = patch(FCM, return_value='msg-1')
        self.fcm = fcm.start()
        self.addCleanup(fcm.stop)

    # ── the admin's actions, as the admin site performs them ─────────────────

    def admin_post(self, **form):
        """Submits the service's edit form. Any job it queued runs, as a worker would run it (it must queue none)."""
        self.client.force_login(self.staff)
        data = {'category': self.makeup.pk, 'name': 'Diwali Special', 'description': form.pop('description', ''), **form}
        with patch(QUEUE, side_effect=lambda *a, **kw: notify_artists_service_announced(*kw['args'])):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.diwali.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.diwali.refresh_from_db()

    def switch_on(self, **form):
        self.admin_post(is_active='on', **form)

    def switch_off(self):
        self.admin_post()

    def announce_and_send(self, message=WORDING):
        """What the admin's announce action does: record the announcement, queue the job, the worker runs it."""
        stamp = ServiceSubCategory.announce_to_artists(self.diwali.pk, message)
        with patch(QUEUE, side_effect=lambda *a, **kw: notify_artists_service_announced(*kw['args'])):
            ServiceSubCategory.dispatch_artist_announcement(self.diwali.pk, stamp)
        self.diwali.refresh_from_db()

    def told(self, user):
        return Notification.objects.filter(user_id=user.user_id, type=TYPE).count()

    # ── Administration ───────────────────────────────────────────────────────

    def test_the_status_persists_and_shows_after_a_refresh(self):
        self.switch_on()
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.diwali.pk).is_active)
        page = self.client.get(reverse('admin:core_servicesubcategory_change', args=[self.diwali.pk]))
        self.assertRegex(page.content.decode(), r'name="is_active"[^>]*checked')
        self.switch_off()
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.diwali.pk).is_active)

    def test_only_authorised_staff_can_change_it(self):
        for user in (None, get_user_model().objects.create_user(username='plain', password='x'),):
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.diwali.pk]),
                             {'category': self.makeup.pk, 'name': 'Diwali Special', 'is_active': 'on'})
        viewer = get_user_model().objects.create_user(username='viewer', password='x', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_servicesubcategory'))
        self.client.force_login(viewer)
        self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.diwali.pk]),
                         {'category': self.makeup.pk, 'name': 'Diwali Special', 'is_active': 'on'})
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.diwali.pk).is_active)
        # an app token has no way to change it through the API
        for client in (self.customer_client, self.artist_client):
            for method in ('put', 'post', 'patch', 'delete'):
                self.assertIn(getattr(client, method)('/core/service-sub-category/get/', {}, format='json').status_code, (400, 405))
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.diwali.pk).is_active)
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)

    # ── The story ────────────────────────────────────────────────────────────

    def test_the_whole_story(self):
        # 0. Off: it cannot be announced, added or booked.
        with self.assertRaises(ValueError):
            ServiceSubCategory.announce_to_artists(self.diwali.pk, WORDING)
        self.assertEqual(self.artist_client.post('/artists/services/add/', {'sub_category_id': self.diwali.pk}, format='json').status_code, 400)
        self.assertEqual(self.book(self.diwali_pkg).status_code, 400)

        # 1. Switching it on notifies nobody: that is a separate, explicit step.
        self.switch_on()
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)
        self.fcm.assert_not_called()
        self.assertIsNone(self.diwali.artists_announced_at)

        # 2. The admin announces it: approved artists (only) are told, once, in the admin's words.
        self.announce_and_send()
        self.assertEqual((self.told(self.artist_user), self.told(self.other_user)), (1, 1))
        for left_out in (self.new_user, self.customer):
            self.assertEqual(self.told(left_out), 0)
        item = self.artist_client.get('/notifications/get_all/').data['data']['data'][0]
        self.assertEqual((item['type'], item['message'], item['referenceId']), (TYPE, WORDING, self.diwali.pk))
        self.fcm.assert_called_once()                                          # one push: only the artist with a device
        self.assertEqual(self.fcm.call_args.args[0].token, 'artist-device')
        self.assertEqual(self.customer_client.get('/notifications/get_all/').data['data']['data'], [])

        # 3. The notification added nothing for anyone: the artist chooses to, through the existing API.
        self.assertEqual(ArtistServiceOffering.objects.filter(sub_category=self.diwali).count(), 0)
        added = self.artist_client.post('/artists/services/add/', {'sub_category_id': self.diwali.pk}, format='json')
        self.assertEqual(added.status_code, 201)
        self.assertEqual(ArtistServiceOffering.objects.filter(sub_category=self.diwali).count(), 1)
        self.assertEqual(self.book(self.diwali_pkg).status_code, 201)

        # 4. Saving, editing or re-activating it afterwards tells nobody again.
        self.switch_on(description='Festive looks')
        self.switch_off()
        self.switch_on()
        self.assertEqual((self.told(self.artist_user), self.told(self.other_user)), (1, 1))

        # 5. Re-sending is a new, explicit announcement and reaches everyone eligible once more.
        self.announce_and_send('Last call for Diwali bookings!')
        self.assertEqual((self.told(self.artist_user), self.told(self.other_user)), (2, 2))

        # 6. Switched off: new additions stop and it can no longer be announced; what exists is untouched.
        self.switch_off()
        with self.assertRaises(ValueError):
            ServiceSubCategory.announce_to_artists(self.diwali.pk, WORDING)
        self.assertEqual(self.other_client.post('/artists/services/add/', {'sub_category_id': self.diwali.pk}, format='json').status_code, 400)
        self.assertEqual(ArtistServiceOffering.objects.filter(sub_category=self.diwali).count(), 1)
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.bridal.pk).is_active)      # siblings untouched

    # ── Failures never corrupt the status ────────────────────────────────────

    def test_a_push_outage_leaves_the_service_on_and_the_in_app_notification_in_place(self):
        self.switch_on()
        self.fcm.side_effect = Exception('FCM is down')
        self.announce_and_send()
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.diwali.pk).is_active)
        self.assertEqual(self.told(self.artist_user), 1)
        self.assertEqual(Notification.objects.get(user_id=self.artist_user.user_id, type=TYPE).delivery_status, 'failed')

    def test_a_dead_job_queue_keeps_the_announcement_and_it_is_sent_later(self):
        from datetime import timedelta
        from django.utils import timezone
        from sunndari_apps.core.tasks import redispatch_unnotified_artist_announcements
        self.switch_on()
        stamp = ServiceSubCategory.announce_to_artists(self.diwali.pk, WORDING)
        with patch(QUEUE, side_effect=ConnectionError('broker down')):
            self.assertFalse(ServiceSubCategory.dispatch_artist_announcement(self.diwali.pk, stamp))
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)
        ServiceSubCategory.objects.filter(pk=self.diwali.pk).update(artists_announced_at=timezone.now() - timedelta(minutes=10))
        with patch('sunndari_apps.core.tasks.notify_artists_service_announced.delay',
                   side_effect=lambda pk, iso: notify_artists_service_announced(pk, iso)):
            self.assertEqual(redispatch_unnotified_artist_announcements(), 1)
        self.assertEqual((self.told(self.artist_user), self.told(self.other_user)), (1, 1))

    # ── Legacy data ──────────────────────────────────────────────────────────

    def test_services_that_existed_before_never_announced_stay_silent_and_work_as_before(self):
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 0)
        self.assertEqual(self.book(self.bridal_pkg).status_code, 201)


class CompleteFlowTest(_Fixture):
    """The whole feature in the order the business runs it, through the admin form and the public APIs only:
    admin creates and announces -> artists are notified and see the popup -> an artist adds it and a package ->
    customers can finally see and book it."""

    def setUp(self):
        super().setUp()
        self.staff = get_user_model().objects.create_superuser(username='ops', email='ops@example.com', password='x')
        self.other_client, self.other_user, self.other_profile = make_artist(phone_number='+919800000020', name='Second Artist')
        for target in ('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification',
                       'sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        fcm = patch(FCM, return_value='msg-1')
        self.fcm = fcm.start()
        self.addCleanup(fcm.stop)

    def test_admin_announces_artist_adds_customer_books(self):
        popup = '/core/service-sub-category/recently_activated/'
        listing = '/core/service-sub-category/get_all/'
        self.client.force_login(self.staff)

        # 1. The admin creates "Diwali Special" and, in the same save, ticks "Send notification to artists".
        with patch(QUEUE, side_effect=lambda *a, **kw: notify_artists_service_announced(*kw['args'])):
            with self.captureOnCommitCallbacks(execute=True):
                created = self.client.post(reverse('admin:core_servicesubcategory_add'), {
                    'category': self.makeup.pk, 'name': 'Diwali Special', 'description': 'Festive looks', 'is_active': 'on',
                    'notify_artists': 'on', 'artists_message': WORDING})
        self.assertEqual(created.status_code, 302)
        diwali = ServiceSubCategory.objects.get(name='Diwali Special')

        # 2. Both approved artists are notified with the admin's words; the customer is not.
        for user in (self.artist_user, self.other_user):
            note = Notification.objects.get(user_id=user.user_id, type=TYPE)
            self.assertEqual((note.message, note.reference_id), (WORDING, diwali.pk))
        self.assertEqual(Notification.objects.filter(user_id=self.customer.user_id).count(), 0)

        # 3. Both artists get the popup; the customer cannot use it and cannot see the service yet.
        for client in (self.artist_client, self.other_client):
            items = client.get(popup).data['data']
            self.assertEqual([(i['name'], i['message']) for i in items], [('Diwali Special', WORDING)])
        self.assertEqual(self.customer_client.get(popup).status_code, 400)
        self.assertNotIn('Diwali Special', self.names(self.customer_client, listing))
        self.assertIn('Diwali Special', self.names(self.artist_client, listing))

        # 4. The first artist adds the service and a package through the existing APIs.
        self.assertEqual(self.artist_client.post('/artists/services/add/', {'sub_category_id': diwali.pk}, format='json').status_code, 201)
        package = self.artist_client.post('/artists/packages/create/', {
            'sub_category_id': diwali.pk, 'name': 'Diwali Glam', 'price': '2200', 'duration_minutes': 90}, format='json')
        self.assertEqual(package.status_code, 201, package.data)

        # 5. It drops out of that artist's popup but stays in the other's; customers now see it and can find the artist.
        self.assertEqual(self.artist_client.get(popup).data['data'], [])
        self.assertEqual(len(self.other_client.get(popup).data['data']), 1)
        self.assertIn('Diwali Special', self.names(self.customer_client, listing))
        found = self.customer_client.get('/customers/artists/search/', {'sub_category_id': diwali.pk}).data['data']['data']
        self.assertEqual([row['artistId'] for row in found], [self.profile.artist_id])

        # 6. Switching it off hides it from everyone but admins; the notification and history remain untouched.
        diwali.refresh_from_db()
        diwali.is_active = False
        diwali.save()
        self.assertNotIn('Diwali Special', self.names(self.customer_client, listing))
        self.assertEqual(self.other_client.get(popup).data['data'], [])
        self.assertEqual(Notification.objects.filter(type=TYPE).count(), 2)
