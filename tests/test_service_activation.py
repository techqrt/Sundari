"""Task 1 of the service-activation feature: the model rule that stamps `activated_at`.

Only a genuine inactive -> active change (or a service created active) starts the 15-day "recently activated"
window. Everything else must leave the timestamps exactly as they were."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory


class ActivationRuleTest(TestCase):

    def setUp(self):
        self.category = ServiceCategory.objects.create(name='Makeup')

    def make(self, name='Bridal Makeup', **extra):
        return ServiceSubCategory.objects.create(category=self.category, name=name, **extra)

    def fresh(self, service):
        return ServiceSubCategory.objects.get(pk=service.pk)

    # ── creation ─────────────────────────────────────────────────────────────

    def test_a_service_created_active_is_stamped_as_just_activated(self):
        before = timezone.now()
        service = self.make()
        self.assertTrue(before <= self.fresh(service).activated_at <= timezone.now())
        self.assertIsNone(self.fresh(service).artists_announced_at)               # creating a service announces nothing

    def test_a_service_created_inactive_has_no_activation_time(self):
        self.assertIsNone(self.fresh(self.make(is_active=False)).activated_at)

    # ── the real transitions ─────────────────────────────────────────────────

    def test_inactive_to_active_sets_the_activation_time(self):
        service = self.make(is_active=False)
        service.is_active = True
        service.save()
        self.assertIsNotNone(self.fresh(service).activated_at)

    def test_reactivating_after_a_deactivation_restarts_the_window(self):
        service = self.make()
        old = timezone.now() - timedelta(days=40)
        ServiceSubCategory.objects.filter(pk=service.pk).update(activated_at=old)
        service = self.fresh(service)
        service.is_active = False
        service.save()
        service.is_active = True
        service.save()
        self.assertGreater(self.fresh(service).activated_at, old + timedelta(days=39))

    # ── things that must NOT count as an activation ──────────────────────────

    def test_saving_an_already_active_service_changes_nothing(self):
        service = self.make()
        stamp = timezone.now() - timedelta(days=3)
        ServiceSubCategory.objects.filter(pk=service.pk).update(activated_at=stamp)
        service = self.fresh(service)
        service.save()
        service.description = 'edited'
        service.name = 'Bridal Makeup 2'
        service.save()
        result = self.fresh(service)
        self.assertEqual(result.activated_at, stamp)

    def test_deactivating_keeps_the_history(self):
        service = self.make()
        stamp = self.fresh(service).activated_at
        service.is_active = False
        service.save()
        result = self.fresh(service)
        self.assertEqual((result.is_active, result.activated_at), (False, stamp))

    def test_saving_an_inactive_service_without_activating_it_changes_nothing(self):
        service = self.make(is_active=False)
        service.description = 'edited'
        service.save()
        self.assertIsNone(self.fresh(service).activated_at)

    def test_a_stale_copy_cannot_restart_the_window_of_a_service_already_activated(self):
        service = self.make(is_active=False)
        stale = self.fresh(service)                       # one admin opens the edit form while it is inactive
        other = self.fresh(service)                       # another admin activates it first
        other.is_active = True
        other.save()
        first_stamp = self.fresh(service).activated_at
        stale.is_active = True                            # the first admin submits their form afterwards
        stale.save()
        self.assertEqual(self.fresh(service).activated_at, first_stamp)

    def test_a_partial_save_that_does_not_include_is_active_changes_nothing(self):
        service = self.make(is_active=False)
        service.name = 'Renamed'
        service.is_active = True                          # changed on the instance, but not being saved
        service.save(update_fields=['name'])
        result = self.fresh(service)
        self.assertEqual((result.name, result.is_active, result.activated_at), ('Renamed', False, None))

    def test_a_partial_save_that_does_include_is_active_stamps_the_time(self):
        service = self.make(is_active=False)
        service.is_active = True
        service.save(update_fields=['is_active'])
        self.assertIsNotNone(self.fresh(service).activated_at)

    # ── safety ───────────────────────────────────────────────────────────────

    def test_the_timestamps_cannot_be_set_through_forms_or_serializers(self):
        from django import forms
        class Form(forms.ModelForm):
            class Meta:
                model = ServiceSubCategory
                fields = '__all__'
        self.assertNotIn('activated_at', Form().fields)
        self.assertNotIn('artists_announced_at', Form().fields)

    def test_the_stamp_uses_the_server_clock(self):
        fixed = timezone.now() - timedelta(days=9)
        with patch('sunndari_apps.core.models.service_sub_category.timezone.now', return_value=fixed):
            service = self.make()
        self.assertEqual(self.fresh(service).activated_at, fixed)

    def test_existing_api_output_is_unchanged(self):
        # activated_at is not exposed by the existing endpoints (a later task adds its own endpoint)
        self.assertNotIn('activated_at', ServiceSubCategory.get(self.make().sub_category_id))


# ─── Task 2: Django admin ─────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse


class ServiceAdminTest(TestCase):

    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(username='svc-admin', email='a@example.com', password='x')
        self.client.force_login(self.admin_user)
        self.category = ServiceCategory.objects.create(name='Makeup')
        self.service = ServiceSubCategory.objects.create(category=self.category, name='Bridal Makeup', is_active=False)

    def fresh(self, service=None):
        return ServiceSubCategory.objects.get(pk=(service or self.service).pk)

    def change_url(self, service=None):
        return reverse('admin:core_servicesubcategory_change', args=[(service or self.service).pk])

    def submit(self, service=None, **overrides):
        service = service or self.fresh()
        data = {'category': service.category_id, 'name': service.name, 'description': service.description or ''}
        if service.is_active:
            data['is_active'] = 'on'
        data.update(overrides)
        return self.client.post(self.change_url(service), data)

    def run_action(self, name, *services):
        return self.client.post(reverse('admin:core_servicesubcategory_changelist'), {
            'action': name, '_selected_action': [s.pk for s in services]}, follow=True)

    # ── list and edit page ───────────────────────────────────────────────────

    def test_the_list_shows_name_category_status_and_activation_time(self):
        live = ServiceSubCategory.objects.create(category=self.category, name='Party Makeup')
        page = self.client.get(reverse('admin:core_servicesubcategory_changelist'))
        self.assertEqual(page.status_code, 200)
        for text in ('Bridal Makeup', 'Party Makeup', 'Makeup'):
            self.assertContains(page, text)
        self.assertContains(page, 'Activate selected services')
        self.assertContains(page, 'Deactivate selected services')
        self.assertTrue(self.client.get(reverse('admin:core_servicesubcategory_changelist'), {'is_active__exact': '0'}).status_code == 200)

    def test_the_list_can_be_filtered_and_searched(self):
        ServiceSubCategory.objects.create(category=self.category, name='Party Makeup')
        url = reverse('admin:core_servicesubcategory_changelist')
        inactive_only = self.client.get(url, {'is_active__exact': '0'})
        self.assertContains(inactive_only, 'Bridal Makeup')
        self.assertNotContains(inactive_only, 'Party Makeup')
        self.assertNotContains(self.client.get(url, {'q': 'party'}), 'Bridal Makeup')

    def test_the_edit_page_has_the_active_checkbox_and_shows_activation_time_read_only(self):
        page = self.client.get(self.change_url())
        self.assertContains(page, 'name="is_active"')
        self.assertNotContains(page, 'name="activated_at"')            # displayed, but not an input
        self.assertContains(page, 'Activated at')

    # ── the checkbox ─────────────────────────────────────────────────────────

    def test_ticking_active_activates_the_service_and_unticking_deactivates_it(self):
        self.assertEqual(self.submit(is_active='on').status_code, 302)
        activated = self.fresh()
        self.assertTrue(activated.is_active)
        self.assertIsNotNone(activated.activated_at)
        stamp = activated.activated_at
        self.submit(is_active='')                                        # untick
        deactivated = self.fresh()
        self.assertFalse(deactivated.is_active)
        self.assertEqual(deactivated.activated_at, stamp)                # history kept

    def test_saving_an_active_service_again_does_not_restart_the_window(self):
        self.submit(is_active='on')
        stamp = self.fresh().activated_at
        ServiceSubCategory.objects.filter(pk=self.service.pk).update(activated_at=stamp - timedelta(days=5))
        stamp = self.fresh().activated_at
        self.submit(is_active='on', description='just a wording change')
        self.assertEqual(self.fresh().activated_at, stamp)

    def test_the_activation_time_cannot_be_set_through_the_form(self):
        self.submit(is_active='on', activated_at='2020-01-01 00:00:00', artists_announced_at='2020-01-01 00:00:00')
        service = self.fresh()
        self.assertGreater(service.activated_at.year, 2020)
        self.assertIsNone(service.artists_announced_at)                         # nor can an announcement be forged

    def test_deactivating_a_service_leaves_its_parent_category_and_siblings_active(self):
        sibling = ServiceSubCategory.objects.create(category=self.category, name='Party Makeup')
        live = ServiceSubCategory.objects.create(category=self.category, name='HD Makeup')
        self.submit(live, is_active='')                                   # untick HD Makeup
        self.assertFalse(self.fresh(live).is_active)
        self.assertTrue(ServiceCategory.objects.get(pk=self.category.pk).is_active)
        self.assertTrue(self.fresh(sibling).is_active)

    # ── bulk actions ─────────────────────────────────────────────────────────

    def test_activate_selected_activates_inactive_services_only(self):
        other = ServiceSubCategory.objects.create(category=self.category, name='Party Makeup', is_active=False)
        live = ServiceSubCategory.objects.create(category=self.category, name='HD Makeup')
        old = timezone.now() - timedelta(days=9)
        ServiceSubCategory.objects.filter(pk=live.pk).update(activated_at=old)
        page = self.run_action('activate_selected', self.service, other, live)
        self.assertTrue(self.fresh(self.service).is_active and self.fresh(other).is_active)
        self.assertIsNotNone(self.fresh(self.service).activated_at)
        self.assertEqual(self.fresh(live).activated_at, old)             # already live: window not restarted
        self.assertContains(page, '2 service(s) activated.')
        self.assertContains(page, '1 already active, left unchanged.')

    def test_deactivate_selected_deactivates_active_services_and_keeps_history(self):
        live = ServiceSubCategory.objects.create(category=self.category, name='HD Makeup')
        stamp = self.fresh(live).activated_at
        page = self.run_action('deactivate_selected', live, self.service)
        self.assertFalse(self.fresh(live).is_active)
        self.assertEqual(self.fresh(live).activated_at, stamp)
        self.assertContains(page, '1 service(s) deactivated.')
        self.assertContains(page, '1 already inactive, left unchanged.')

    def test_the_bulk_action_never_touches_the_parent_category(self):
        live = ServiceSubCategory.objects.create(category=self.category, name='HD Makeup')
        self.run_action('deactivate_selected', live)
        self.assertTrue(ServiceCategory.objects.get(pk=self.category.pk).is_active)

    # ── who may do it ────────────────────────────────────────────────────────

    def test_anonymous_and_non_staff_users_cannot_reach_the_service_admin(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.change_url()).status_code, 302)          # to the login page
        member = get_user_model().objects.create_user(username='plain', password='x', is_staff=False)
        self.client.force_login(member)
        self.assertEqual(self.client.post(self.change_url(), {'category': self.category.pk, 'name': 'X', 'is_active': 'on'}).status_code, 302)
        self.assertFalse(self.fresh().is_active)

    def test_staff_without_change_permission_cannot_activate(self):
        staff = get_user_model().objects.create_user(username='viewer', password='x', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_servicesubcategory'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.change_url()).status_code, 200)            # may look
        denied = self.client.post(self.change_url(), {'category': self.category.pk, 'name': 'Bridal Makeup', 'is_active': 'on'})
        self.assertEqual(denied.status_code, 403)
        self.run_action('activate_selected', self.service)
        self.assertFalse(self.fresh().is_active)

    def test_the_existing_category_and_other_core_admin_pages_still_work(self):
        for name in ('core_servicecategory', 'core_locationtype', 'core_brand', 'core_bookingstatus'):
            self.assertEqual(self.client.get(reverse(f'admin:{name}_changelist')).status_code, 200, name)
