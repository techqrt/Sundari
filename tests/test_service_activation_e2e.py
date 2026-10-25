"""The acceptance checklist of the service-activation feature, walked as one story through the real entry
points: the Django admin form, the queued notification job, and the customer-facing APIs."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ServiceSubCategory
from sunndari_apps.core.tasks import notify_service_activated
from sunndari_apps.notifications.models.notification import Notification

from tests.test_customers import make_package
from tests.test_service_inactive_rules import _Fixture

QUEUE = 'sunndari_apps.core.tasks.notify_service_activated.apply_async'
POPUP = '/core/service-sub-category/recently_activated/'
FCM = 'sunndari_apps.notifications.utils.messaging.send'


class AcceptanceFlowTest(_Fixture):
    """A brand-new service ('Lash Extensions') that an artist already has a package for."""

    def setUp(self):
        super().setUp()
        # The baseline services stand for the ones that already existed before activation was tracked (activated_at is
        # NULL on those in a real database), so only 'Lash Extensions' can ever be new in this story.
        ServiceSubCategory.objects.filter(pk__in=[self.bridal.pk, self.party.pk, self.cut.pk]).update(activated_at=None)
        self.lash = ServiceSubCategory.objects.create(category=self.makeup, name='Lash Extensions', is_active=False)
        self.lash_pkg = make_package(self.profile, sub_category=self.lash, price=1800, name='Lash Package')
        User.objects.filter(pk=self.customer.pk).update(fcm_token='device-1')
        self.second_client, self.second = self._customer('+919800000010')
        self.staff = get_user_model().objects.create_superuser(username='ops', email='ops@example.com', password='x')
        for target in ('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification',
                       'sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        fcm = patch(FCM, return_value='msg-1')
        self.fcm = fcm.start()
        self.addCleanup(fcm.stop)

    def _customer(self, phone):
        from tests.test_customers import make_customer
        return make_customer(phone_number=phone)

    # ── the admin's actions, as the admin site performs them ─────────────────

    def admin_post(self, **form):
        """Submits the service's edit form and lets the queued job run, as a worker would."""
        self.client.force_login(self.staff)
        data = {'category': self.makeup.pk, 'name': 'Lash Extensions', 'description': form.pop('description', ''), **form}
        with patch(QUEUE, side_effect=lambda args, **kw: notify_service_activated(*args)):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.lash.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.lash.refresh_from_db()

    def switch_on(self, **form):
        self.admin_post(is_active='on', **form)

    def switch_off(self):
        self.admin_post()

    def popup(self, client=None):
        return [row['name'] for row in (client or self.customer_client).get(POPUP).data['data']]

    def notifications(self, user=None):
        return Notification.objects.filter(user_id=(user or self.customer).user_id, type='service_activated').count()

    # ── Administration ────────────────────────────────────────────────────────

    def test_the_status_persists_and_shows_after_a_refresh(self):
        self.switch_on()
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)
        page = self.client.get(reverse('admin:core_servicesubcategory_change', args=[self.lash.pk]))
        self.assertContains(page, 'name="is_active"')
        self.assertRegex(page.content.decode(), r'name="is_active"[^>]*checked')
        self.switch_off()
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)

    def test_only_authorised_staff_can_change_it(self):
        for user in (None, get_user_model().objects.create_user(username='plain', password='x'),):
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.lash.pk]),
                             {'category': self.makeup.pk, 'name': 'Lash Extensions', 'is_active': 'on'})
        viewer = get_user_model().objects.create_user(username='viewer', password='x', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_servicesubcategory'))
        self.client.force_login(viewer)
        self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.lash.pk]),
                         {'category': self.makeup.pk, 'name': 'Lash Extensions', 'is_active': 'on'})
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)
        self.assertEqual(self.notifications(), 0)
        # a customer or artist token has no way to change it through the API
        for client in (self.customer_client, self.artist_client):
            for method in ('put', 'post', 'patch', 'delete'):
                self.assertIn(getattr(client, method)('/core/service-sub-category/get/', {}, format='json').status_code, (400, 405))
        self.assertFalse(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)

    # ── Notifications + the popup, in the order a real week would go ─────────

    def test_the_whole_story(self):
        # 0. Off: customers see nothing of it anywhere.
        self.assertEqual(self.popup(), [])
        self.assertNotIn('Lash Extensions', self.names(self.customer_client, '/core/service-sub-category/get_all/'))
        self.assertEqual(self.book(self.lash_pkg).status_code, 400)

        # 1. An admin switches it on: customers (only) are told once, and it is "new".
        self.switch_on()
        self.assertEqual((self.notifications(), self.notifications(self.second)), (1, 1))
        self.assertEqual(Notification.objects.filter(type='service_activated', user_id__in=[self.artist_user.user_id]).count(), 0)
        self.assertEqual(self.popup(), ['Lash Extensions'])
        self.assertEqual(self.popup(self.second_client), ['Lash Extensions'])
        self.assertIn('Lash Extensions', self.names(self.customer_client, '/core/service-sub-category/get_all/'))
        self.fcm.assert_called_once()                                         # one push: only the customer with a device

        # 2. The popup's service opens the existing search and the booking flow.
        found = self.customer_client.get('/customers/artists/search/', {'sub_category_id': self.lash.pk}).data['data']['data']
        self.assertEqual([row['artistId'] for row in found], [self.profile.artist_id])
        self.assertEqual(self.book(self.lash_pkg).status_code, 201)

        # 3. Saving again, or editing anything else, announces nothing new.
        self.switch_on()
        self.switch_on(description='Classic and volume sets')
        self.assertEqual(self.notifications(), 1)

        # 4. Reading the notification changes nothing about the popup (and vice versa).
        self.customer_client.put('/notifications/mark_all_read/', {}, format='json')
        self.assertEqual(self.popup(), ['Lash Extensions'])

        # 5. Switching it off: no notification, gone from the popup and lists, new bookings stop, old ones remain.
        self.switch_off()
        self.assertEqual(self.notifications(), 1)
        self.assertEqual(self.popup(), [])
        self.assertNotIn('Lash Extensions', self.names(self.customer_client, '/core/service-sub-category/get_all/'))
        self.assertEqual(self.book(self.lash_pkg, client=self.second_client).status_code, 400)
        self.assertEqual(len(self.customer_client.get('/customers/bookings/get_all/').data['data']['data']), 1)
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.bridal.pk).is_active)          # siblings untouched

        # 6. Switching it back on starts a fresh window and tells customers again.
        self.switch_on()
        self.assertEqual(self.notifications(), 2)
        self.assertEqual(self.popup(), ['Lash Extensions'])

        # 7. After 15 days it is no longer new, but it is still live and bookable.
        ServiceSubCategory.objects.filter(pk=self.lash.pk).update(activated_at=timezone.now() - timedelta(days=15, minutes=1))
        self.assertEqual(self.popup(), [])
        self.assertIn('Lash Extensions', self.names(self.customer_client, '/core/service-sub-category/get_all/'))
        later = self.second_client.post('/customers/bookings/create/', {
            'artist_id': self.profile.artist_id, 'package_id': self.lash_pkg.package_id,
            'location_type_id': self.location.location_type_id,
            'booking_date': self.day.strftime('%d-%m-%y'), 'start_time': '15:00:00'}, format='json')
        self.assertEqual(later.status_code, 201)                              # a different slot from the first booking

    # ── Failures never corrupt the status ────────────────────────────────────

    def test_a_push_outage_leaves_the_service_on_and_the_in_app_notification_in_place(self):
        self.fcm.side_effect = Exception('FCM is down')
        self.switch_on()
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)
        self.assertEqual(self.notifications(), 1)
        self.assertEqual(Notification.objects.get(user_id=self.customer.user_id, type='service_activated').delivery_status, 'failed')
        self.assertEqual(self.popup(), ['Lash Extensions'])

    def test_a_dead_job_queue_leaves_the_service_on_and_it_is_announced_later(self):
        from sunndari_apps.core.tasks import redispatch_unnotified_service_activations
        self.client.force_login(self.staff)
        with patch(QUEUE, side_effect=ConnectionError('broker down')):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('admin:core_servicesubcategory_change', args=[self.lash.pk]), {
                    'category': self.makeup.pk, 'name': 'Lash Extensions', 'description': '', 'is_active': 'on'})
        self.assertTrue(ServiceSubCategory.objects.get(pk=self.lash.pk).is_active)
        self.assertEqual(self.notifications(), 0)
        ServiceSubCategory.objects.filter(pk=self.lash.pk).update(activated_at=timezone.now() - timedelta(minutes=10))
        with patch('sunndari_apps.core.tasks.notify_service_activated.delay',
                   side_effect=lambda pk, iso: notify_service_activated(pk, iso)):
            self.assertEqual(redispatch_unnotified_service_activations(), 1)
        self.assertEqual(self.notifications(), 1)

    # ── Legacy data ──────────────────────────────────────────────────────────

    def test_services_that_existed_before_tracking_are_never_shown_as_new(self):
        ServiceSubCategory.objects.filter(pk__in=[self.bridal.pk, self.party.pk, self.cut.pk]).update(activated_at=None)
        self.assertEqual(self.popup(), [])
        self.assertEqual(self.book(self.bridal_pkg).status_code, 201)         # and they work as before
