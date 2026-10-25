"""Randomized simulation of the service-activation feature with an independent model of what must be true.

Each run performs hundreds of random actions - creating services, switching them and their categories on and
off, adding customers, jumping forward in time, losing / duplicating / failing notification jobs - and after
EVERY step checks the rules from outside, using only what it observed and its own bookkeeping:

  I1  activated_at changes exactly when a service goes from off to on (or is created on) - never otherwise
  I2  a notification is only ever made for an active customer, about a service that is live at that moment,
      and never twice within one activation
  I3  across activations a customer is told again only after a newer activation
  I4  the "new services" list equals an independent computation (live, activated < 15 days ago, newest first)
  I5  customers see exactly the live services; admins see all
  I6  at the end, once lost jobs have been re-dispatched, every recent live service has told every customer who
      was there when it went live - exactly once

The generator is seeded, so any failure replays exactly."""
import collections
import random
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ServiceCategory, ServiceSubCategory
from sunndari_apps.core.tasks import notify_service_activated, redispatch_unnotified_service_activations
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService

from tests.test_customers import make_artist, make_customer, make_user
from tests.test_help_center import make_admin

TYPE = 'service_activated'
QUEUE = 'sunndari_apps.core.tasks.notify_service_activated.apply_async'


class Simulation(TestCase):
    STEPS = 300

    # ── world ────────────────────────────────────────────────────────────────

    def build_world(self, seed):
        self.rng = random.Random(seed)
        self.op = 0
        self.queue = []                                   # jobs the broker is holding: (service id, activated_at iso)
        self.problems = []
        self.tally = collections.Counter()
        self.cats = {}                                    # category id -> active
        for name in ('Makeup', 'Hair', 'Nails'):
            self.cats[ServiceCategory.objects.create(name=name).pk] = True
        self.svc = {}                                     # service id -> {'active', 'cat', 'epoch_op', 'history': [stamps]}
        self.custs = {}                                   # user id -> {'born', 'ever_inactive'}
        self.customer_client, base = make_customer(phone_number='+919000000001')
        self.custs[base.user_id] = {'born': 0, 'ever_inactive': False}
        self.artist_client, self.artist_user, _ = make_artist(phone_number='+919000000002')
        self.admin_client, self.admin_user = make_admin(phone_number='+919000000003')
        self.staff = get_user_model().objects.create_superuser(username='sim', email='s@x.com', password='x')
        self.phone = 10
        self.n = 0

    def bad(self, rule, detail):
        self.problems.append(f'[op {self.op}] {rule}: {detail}')

    def db_service(self, sid):
        return ServiceSubCategory.objects.get(pk=sid)

    # ── actions ──────────────────────────────────────────────────────────────

    def save_service(self, sid, **changes):
        """Change a service through save() and let the commit hook queue its job into our fake broker."""
        service = self.db_service(sid)
        for field, value in changes.items():
            setattr(service, field, value)
        with patch(QUEUE, side_effect=lambda args, **kw: self.queue.append(tuple(args))):
            with self.captureOnCommitCallbacks(execute=True):
                service.save()

    def act_create_service(self):
        self.n += 1
        cat = self.rng.choice(list(self.cats))
        active = self.rng.random() < 0.6
        before = timezone.now()
        with patch(QUEUE, side_effect=lambda args, **kw: self.queue.append(tuple(args))):
            with self.captureOnCommitCallbacks(execute=True):
                service = ServiceSubCategory.objects.create(category_id=cat, name=f'Service {self.n}', is_active=active)
        service.refresh_from_db()
        self.svc[service.pk] = {'active': active, 'cat': cat, 'epoch_op': self.op if active else None, 'history': []}
        if active:
            if service.activated_at is None or service.activated_at < before:
                self.bad('I1', f'service {service.pk} created active has activated_at={service.activated_at}')
            self.svc[service.pk]['history'].append(service.activated_at)
        elif service.activated_at is not None:
            self.bad('I1', f'service {service.pk} created inactive has activated_at={service.activated_at}')

    def act_toggle_service(self):
        if not self.svc:
            return
        sid = self.rng.choice(list(self.svc))
        want = self.rng.random() < 0.5
        was = self.svc[sid]['active']
        old = self.db_service(sid).activated_at
        if self.rng.random() < 0.3:                                      # through the admin's bulk action
            self.client.force_login(self.staff)
            with patch(QUEUE, side_effect=lambda args, **kw: self.queue.append(tuple(args))):
                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(reverse('admin:core_servicesubcategory_changelist'), {
                        'action': 'activate_selected' if want else 'deactivate_selected', '_selected_action': [sid]})
        else:
            self.save_service(sid, is_active=want)
        new = self.db_service(sid).activated_at
        self.svc[sid]['active'] = want
        if want and not was:
            self.tally['switched on'] += 1
            self.svc[sid]['epoch_op'] = self.op
            self.svc[sid]['history'].append(new)
            if old is not None and new <= old:
                self.bad('I1', f'service {sid} switched on but activated_at did not move forward ({old} -> {new})')
        elif new != old:
            self.bad('I1', f'service {sid} {"re-saved on" if want else "switched off"} but activated_at changed ({old} -> {new})')

    def act_edit_service(self):
        if not self.svc:
            return
        sid = self.rng.choice(list(self.svc))
        old = self.db_service(sid).activated_at
        self.save_service(sid, description=f'edit {self.op}')
        self.save_service(sid)
        if self.db_service(sid).activated_at != old:
            self.bad('I1', f'an unrelated edit changed activated_at of service {sid}')

    def act_toggle_category(self):
        cid = self.rng.choice(list(self.cats))
        self.cats[cid] = not self.cats[cid]
        ServiceCategory.objects.filter(pk=cid).update(is_active=self.cats[cid])

    def act_add_customer(self):
        self.phone += 1
        user = make_user(f'+9190000{self.phone:05d}', 'customer')
        self.custs[user.user_id] = {'born': self.op, 'ever_inactive': False}

    def act_add_non_customer(self):
        self.phone += 1
        make_user(f'+9190000{self.phone:05d}', self.rng.choice(['artist', 'admin']))

    def act_deactivate_customer(self):
        candidates = [uid for uid in self.custs if uid != self.customer_client.handler._force_user_id] if False else list(self.custs)[1:]
        if candidates:
            uid = self.rng.choice(candidates)
            User.objects.filter(pk=uid).update(is_active=False)
            self.custs[uid]['ever_inactive'] = True

    def act_time_travel(self):
        delta = timedelta(hours=self.rng.choice([1, 3, 20, 30, 24 * 5, 24 * 10, 24 * 16]))
        ServiceSubCategory.objects.exclude(activated_at=None).update(
            activated_at=__import__('django.db.models', fromlist=['F']).F('activated_at') - delta)
        ServiceSubCategory.objects.exclude(activation_notified_at=None).update(
            activation_notified_at=__import__('django.db.models', fromlist=['F']).F('activation_notified_at') - delta)
        Notification.objects.update(created_at=__import__('django.db.models', fromlist=['F']).F('created_at') - delta)
        for state in self.svc.values():
            state['history'] = [stamp - delta for stamp in state['history']]
        # queued jobs keep the stamp they were made with, so they must be shifted too or they would look stale
        self.queue = [(sid, (__import__('datetime').datetime.fromisoformat(iso) - delta).isoformat()) for sid, iso in self.queue]

    # ── the notification job, with failures injected ─────────────────────────

    def run_job(self, args, fail_user=None, crash_on_call=None):
        calls = {'n': 0}
        attempted_failure = {'hit': False}
        real_notify = NotificationService.notify
        real_exists = Notification.exists_for_reference

        def spy_notify(user_id, **kwargs):
            service = self.db_service(kwargs['reference_id'])
            user = User.objects.get(pk=user_id)
            if user.role != 'customer' or not user.is_active:
                self.bad('I2', f'notified user {user_id} who is {user.role}/active={user.is_active}')
            if not (service.is_active and ServiceCategory.objects.get(pk=service.category_id).is_active):
                self.bad('I2', f'notified about service {service.pk} that is not live')
            if Notification.objects.filter(user_id=user_id, type=TYPE, reference_id=service.pk, created_at__gte=service.activated_at).exists():
                self.bad('I2', f'user {user_id} already told about service {service.pk} in this activation')
            if user_id == fail_user:
                attempted_failure['hit'] = True
                return None
            return real_notify(user_id=user_id, **kwargs)

        def exists(*a, **k):
            calls['n'] += 1
            if crash_on_call and calls['n'] == crash_on_call:
                raise RuntimeError('simulated crash')
            return real_exists(*a, **k)

        with patch.object(NotificationService, 'notify', side_effect=spy_notify), \
                patch.object(Notification, 'exists_for_reference', side_effect=exists), \
                patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'):
            try:
                notify_service_activated(*args)
                after = ServiceSubCategory.objects.get(pk=args[0])
                if attempted_failure['hit'] and after.activated_at.isoformat() == args[1] and after.activation_notified_at is not None:
                    self.bad('I2', f'a recipient failed for service {args[0]} but the claim was not handed back, so nobody will retry')
            except Exception:
                if crash_on_call:
                    if ServiceSubCategory.objects.get(pk=args[0]).activation_notified_at is not None and \
                            ServiceSubCategory.objects.get(pk=args[0]).activated_at.isoformat() == args[1]:
                        self.bad('I2', f'a crashed job left service {args[0]} marked as notified')
                else:
                    raise

    def act_job(self):
        if not self.queue:
            return
        roll = self.rng.random()
        index = self.rng.randrange(len(self.queue))
        self.tally['job actions'] += 1
        if roll < 0.15:
            self.tally['jobs lost'] += 1
            self.queue.pop(index)                                          # the broker loses it
        elif roll < 0.30:
            self.tally['jobs delivered twice'] += 1
            self.run_job(self.queue[index])                                # delivered twice: run now, keep for later
        elif roll < 0.42:
            self.tally['jobs crashed'] += 1
            self.run_job(self.queue.pop(index), crash_on_call=self.rng.choice([1, 2, 3]))
        elif roll < 0.55:
            self.tally['jobs with a failing recipient'] += 1
            sid = self.queue[index][0]
            eligible = [uid for uid, info in self.custs.items()
                        if not info['ever_inactive'] and info['born'] < (self.svc[sid]['epoch_op'] or 0)] or list(self.custs)
            self.run_job(self.queue.pop(index), fail_user=self.rng.choice(eligible))
        else:
            self.run_job(self.queue.pop(index))

    def act_redispatch(self):
        with patch('sunndari_apps.core.tasks.notify_service_activated.delay', side_effect=lambda sid, iso: self.queue.append((sid, iso))):
            redispatch_unnotified_service_activations()

    # ── invariants ───────────────────────────────────────────────────────────

    def check(self):
        now = timezone.now()
        db = {s.pk: s for s in ServiceSubCategory.objects.select_related('category')}
        for sid, state in self.svc.items():
            if db[sid].is_active != state['active']:
                self.bad('model', f'service {sid} is_active={db[sid].is_active}, model says {state["active"]}')
        live = {sid for sid, s in db.items() if s.is_active and s.category.is_active}
        expected = sorted(
            (s for s in db.values() if s.pk in live and s.activated_at and now - timedelta(days=15) < s.activated_at <= now),
            key=lambda s: (-s.activated_at.timestamp(), s.pk))
        for who, client in (('customer', self.customer_client), ('artist', self.artist_client), ('admin', self.admin_client)):
            got = [row['subCategoryId'] for row in client.get('/core/service-sub-category/recently_activated/').data['data']]
            self.tally['popup checks'] += 1
            self.tally['popup non-empty'] += bool(got)
            if got != [s.pk for s in expected]:
                self.bad('I4', f'{who} popup {got} != expected {[s.pk for s in expected]}')
        listed = {row['subCategoryId'] for row in self.customer_client.get('/core/service-sub-category/get_all/?limit=200').data['data']['data']}
        if listed != live:
            self.bad('I5', f'customer list {sorted(listed)} != live {sorted(live)}')
        admin_listed = {row['subCategoryId'] for row in self.admin_client.get('/core/service-sub-category/get_all/?limit=200').data['data']['data']}
        if admin_listed != set(db):
            self.bad('I5', 'admin list is not every service')
        for note in Notification.objects.filter(type=TYPE).select_related('user'):
            if note.user.role != 'customer':
                self.bad('I2', f'a {note.user.role} has a service_activated notification')
        per_pair = {}
        for note in Notification.objects.filter(type=TYPE).order_by('created_at', 'pk'):
            per_pair.setdefault((note.user_id, note.reference_id), []).append(note.created_at)
        for (uid, sid), times in per_pair.items():
            history = sorted(self.svc[sid]['history'])
            for earlier, later in zip(times, times[1:]):
                if not any(earlier < stamp <= later for stamp in history):
                    self.bad('I3', f'user {uid} told about service {sid} twice with no new activation between')

    # ── the run ──────────────────────────────────────────────────────────────

    def simulate(self, seed):
        self.build_world(seed)
        actions = [(self.act_create_service, 4), (self.act_toggle_service, 14), (self.act_edit_service, 4),
                   (self.act_toggle_category, 3), (self.act_add_customer, 6), (self.act_add_non_customer, 2),
                   (self.act_deactivate_customer, 1), (self.act_time_travel, 4), (self.act_job, 24), (self.act_redispatch, 3)]
        callables, weights = zip(*actions)
        for self.op in range(1, self.STEPS + 1):
            self.rng.choices(callables, weights)[0]()
            self.check()
            if len(self.problems) > 12:
                break
        self.check_eventual_delivery()
        self.assertEqual(self.problems, [], f'seed {seed}:\n' + '\n'.join(self.problems[:12]))
        # "no problems" only means something if the dice reached the interesting situations
        self.tally['notifications made'] = Notification.objects.filter(type=TYPE).count()
        self.tally['services'] = len(self.svc)
        for name, minimum in (('switched on', 8), ('jobs lost', 1), ('jobs delivered twice', 1), ('jobs crashed', 1),
                              ('jobs with a failing recipient', 1), ('popup non-empty', 20), ('notifications made', 15)):
            self.assertGreaterEqual(self.tally[name], minimum, f'seed {seed}: too little coverage of {name!r}: {dict(self.tally)}')
        print('SIM_COVERAGE', seed, dict(self.tally))

    def check_eventual_delivery(self):
        """I6: after lost jobs are re-dispatched and everything is allowed to run, nothing recent is left half-done."""
        now = timezone.now()
        young = [s for s in ServiceSubCategory.objects.select_related('category')
                 if s.is_active and s.category.is_active and s.activated_at and s.activated_at > now - timedelta(hours=20)]
        for _ in range(8):
            self.act_time_travel_minutes(3)
            self.act_redispatch()
            if not self.queue:
                break
            while self.queue:
                self.run_job(self.queue.pop(0))
        for service in young:
            service.refresh_from_db()
            if service.activation_notified_at is None:
                self.bad('I6', f'recent live service {service.pk} was never announced')
                continue
            epoch_op = self.svc[service.pk]['epoch_op']
            for uid, info in self.custs.items():
                if info['born'] < epoch_op and not info['ever_inactive']:
                    count = Notification.objects.filter(user_id=uid, type=TYPE, reference_id=service.pk, created_at__gte=service.activated_at).count()
                    if count != 1:
                        self.bad('I6', f'customer {uid} has {count} notifications for service {service.pk} (expected exactly 1)')

    def act_time_travel_minutes(self, minutes):
        from django.db.models import F
        delta = timedelta(minutes=minutes)
        ServiceSubCategory.objects.exclude(activated_at=None).update(activated_at=F('activated_at') - delta)
        ServiceSubCategory.objects.exclude(activation_notified_at=None).update(activation_notified_at=F('activation_notified_at') - delta)
        Notification.objects.update(created_at=F('created_at') - delta)
        for state in self.svc.values():
            state['history'] = [stamp - delta for stamp in state['history']]
        from datetime import datetime
        self.queue = [(sid, (datetime.fromisoformat(iso) - delta).isoformat()) for sid, iso in self.queue]

    def test_seed_1(self):
        self.simulate(20261024)

    def test_seed_2(self):
        self.simulate(7)

    def test_seed_3(self):
        self.simulate(424242)
