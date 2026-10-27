"""Randomized simulation of the artist service announcement with an independent model of what must be true.

Each run performs hundreds of random actions - creating services, switching them and their categories on and off,
announcing them to artists (some refused), adding artists in every approval state, jumping forward in time, losing /
duplicating / failing notification jobs - and after EVERY step checks the rules from outside, using only what it
observed and its own bookkeeping:

  I1  activated_at changes exactly when a service goes from off to on (or is created on) - never otherwise
  I2  a notification is only ever made for an approved, active artist, about a service that is live at that moment,
      for the announcement that is current, and never twice within one announcement
  I3  a service nobody announced has told nobody: creating, activating, editing and deactivating (model or admin
      action) queue no job and leave the announcement fields untouched
  I4  an announcement is refused exactly when the service or its category is off
  I5  only artists ever receive it - never customers or admins
  I6  at the end, once lost jobs have been re-dispatched, every recent live announcement has told every artist who
      was eligible when it went out and still is - exactly once

The generator is seeded, so any failure replays exactly."""
import collections
import random
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ApprovalStatus, ServiceCategory, ServiceSubCategory
from sunndari_apps.core.tasks import notify_artists_service_announced, redispatch_unnotified_artist_announcements
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService

from tests.test_customers import make_artist, make_customer, make_user
from tests.test_help_center import make_admin

TYPE = 'service_activated'
QUEUE = 'sunndari_apps.core.tasks.notify_artists_service_announced.apply_async'


class Simulation(TestCase):
    STEPS = 600

    # ── world ────────────────────────────────────────────────────────────────

    def build_world(self, seed):
        self.rng = random.Random(seed)
        self.op = 0
        self.queue = []                                   # jobs the broker is holding: (service id, announced_at iso)
        self.problems = []
        self.tally = collections.Counter()
        self.cats = {}                                    # category id -> active
        for name in ('Makeup', 'Hair', 'Nails'):
            self.cats[ServiceCategory.objects.create(name=name).pk] = True
        # service id -> {'active', 'cat', 'announce_op', 'announced': [stamps]}
        self.svc = {}
        # artist user id -> {'born': op, 'ever_ineligible': bool}; an artist is eligible when approved and active
        self.artists = {}
        self.rejected = ApprovalStatus.objects.get_or_create(name='rejected', defaults={'description': 'Rejected'})[0]
        self.make_customer_user('+919000000001')
        self.admin_client, self.admin_user = make_admin(phone_number='+919000000003')
        self.staff = get_user_model().objects.create_superuser(username='sim', email='s@x.com', password='x')
        self.phone = 10
        self.n = 0
        self.add_artist(approved=True, initial=True)

    def make_customer_user(self, phone):
        return make_customer(phone_number=phone)

    def bad(self, rule, detail):
        self.problems.append(f'[op {self.op}] {rule}: {detail}')

    def db_service(self, sid):
        return ServiceSubCategory.objects.get(pk=sid)

    def announcement_state(self, sid):
        s = self.db_service(sid)
        return (s.artists_announced_at, s.artists_notified_at, s.artists_announcement_message)

    def enqueue_fake(self, *args, **kwargs):
        self.queue.append(tuple(kwargs['args']))

    # ── actions ──────────────────────────────────────────────────────────────

    def quiet(self, action):
        """Runs something that must never queue a notification job, committing as production would."""
        before = len(self.queue)
        with patch(QUEUE, side_effect=self.enqueue_fake):
            with self.captureOnCommitCallbacks(execute=True):
                action()
        if len(self.queue) != before:
            self.bad('I3', 'a save / create / admin activation queued a notification job')

    def save_service(self, sid, **changes):
        service = self.db_service(sid)
        for field, value in changes.items():
            setattr(service, field, value)
        self.quiet(service.save)

    def act_create_service(self):
        self.n += 1
        cat = self.rng.choice(list(self.cats))
        active = self.rng.random() < 0.6
        before = timezone.now()
        holder = {}
        self.quiet(lambda: holder.update(s=ServiceSubCategory.objects.create(category_id=cat, name=f'Service {self.n}', is_active=active)))
        service = holder['s']
        service.refresh_from_db()
        self.svc[service.pk] = {'active': active, 'cat': cat, 'announce_op': None, 'announced': []}
        if active and (service.activated_at is None or service.activated_at < before):
            self.bad('I1', f'service {service.pk} created active has activated_at={service.activated_at}')
        if not active and service.activated_at is not None:
            self.bad('I1', f'service {service.pk} created inactive has activated_at={service.activated_at}')
        if any(self.announcement_state(service.pk)):
            self.bad('I3', f'service {service.pk} has announcement data right after creation')

    def act_toggle_service(self):
        if not self.svc:
            return
        sid = self.rng.choice(list(self.svc))
        want = self.rng.random() < 0.5
        was = self.svc[sid]['active']
        old = self.db_service(sid).activated_at
        frozen = self.announcement_state(sid)
        if self.rng.random() < 0.3:                                      # through the admin's bulk action
            self.client.force_login(self.staff)
            self.quiet(lambda: self.client.post(reverse('admin:core_servicesubcategory_changelist'), {
                'action': 'activate_selected' if want else 'deactivate_selected', '_selected_action': [sid]}))
        else:
            self.save_service(sid, is_active=want)
        new = self.db_service(sid).activated_at
        self.svc[sid]['active'] = want
        if want and not was:
            self.tally['switched on'] += 1
            if old is not None and new <= old:
                self.bad('I1', f'service {sid} switched on but activated_at did not move forward ({old} -> {new})')
        elif new != old:
            self.bad('I1', f'service {sid} {"re-saved on" if want else "switched off"} but activated_at changed ({old} -> {new})')
        if self.announcement_state(sid) != frozen:
            self.bad('I3', f'toggling service {sid} changed its announcement data')

    def act_edit_service(self):
        if not self.svc:
            return
        sid = self.rng.choice(list(self.svc))
        old = self.db_service(sid).activated_at
        frozen = self.announcement_state(sid)
        self.save_service(sid, description=f'edit {self.op}')
        self.save_service(sid)
        if self.db_service(sid).activated_at != old:
            self.bad('I1', f'an unrelated edit changed activated_at of service {sid}')
        if self.announcement_state(sid) != frozen:
            self.bad('I3', f'editing service {sid} changed its announcement data')

    def act_stale_copy_save(self):
        """An admin form left open from before an announcement must not wipe it when it is finally saved."""
        announced = [sid for sid, s in self.svc.items() if s['announced']]
        if not announced:
            return
        sid = self.rng.choice(announced)
        frozen = self.announcement_state(sid)
        stale = self.db_service(sid)
        stale.artists_announced_at = None
        stale.artists_notified_at = None
        stale.artists_announcement_message = None
        stale.description = f'stale {self.op}'
        self.quiet(stale.save)
        if self.announcement_state(sid) != frozen:
            self.bad('I3', f'a stale copy saved over the announcement of service {sid}')

    def act_toggle_category(self):
        cid = self.rng.choice(list(self.cats))
        self.cats[cid] = not self.cats[cid]
        ServiceCategory.objects.filter(pk=cid).update(is_active=self.cats[cid])

    def act_announce(self):
        if not self.svc:
            return
        live_ids = [s for s, v in self.svc.items() if v['active'] and self.cats[v['cat']]]
        # mostly announce live services (that is the admin's normal use) but keep trying hidden ones to prove they are refused
        sid = self.rng.choice(live_ids if live_ids and self.rng.random() < 0.75 else list(self.svc))
        live = self.svc[sid]['active'] and self.cats[self.svc[sid]['cat']]
        message = self.rng.choice(['', 'Festive season! Add this service.', 'x' * 300])
        try:
            stamp = ServiceSubCategory.announce_to_artists(sid, message)
        except ValueError:
            self.tally['announcements refused'] += 1
            if live:
                self.bad('I4', f'announcing live service {sid} was refused')
            return
        if not live:
            self.bad('I4', f'announcing service {sid}, which is not live, was accepted')
        self.tally['announcements'] += 1
        self.svc[sid]['announced'].append(stamp)
        self.svc[sid]['announce_op'] = self.op
        if self.rng.random() < 0.9:                                      # the admin action queues the job
            with patch(QUEUE, side_effect=self.enqueue_fake):
                ServiceSubCategory.dispatch_artist_announcement(sid, stamp)

    def add_artist(self, approved, initial=False):
        self.phone += 1
        _, user, profile = make_artist(phone_number=f'+9190000{self.phone:05d}', approved=approved)
        self.artists[user.user_id] = {'born': 0 if initial else self.op, 'ever_ineligible': not approved}

    def act_add_artist(self):
        self.add_artist(approved=self.rng.random() < 0.7)

    def act_add_non_artist(self):
        self.phone += 1
        make_user(f'+9190000{self.phone:05d}', self.rng.choice(['customer', 'admin']))

    def act_spoil_artist(self):
        """An artist stops being eligible (rejected or deactivated); the model remembers it forever."""
        candidates = [uid for uid, info in self.artists.items() if not info['ever_ineligible']]
        if not candidates:
            return
        uid = self.rng.choice(candidates)
        if self.rng.random() < 0.5:
            User.objects.filter(pk=uid).update(is_active=False)
        else:
            from sunndari_apps.artists.models import ArtistProfile
            ArtistProfile.objects.filter(user_id=uid).update(approval_status=self.rejected)
        self.artists[uid]['ever_ineligible'] = True

    def act_time_travel(self):
        self.shift(timedelta(hours=self.rng.choice([1, 3, 20, 30, 24 * 5, 24 * 10, 24 * 16])))

    def shift(self, delta):
        for field in ('activated_at', 'artists_announced_at', 'artists_notified_at'):
            ServiceSubCategory.objects.exclude(**{field: None}).update(**{field: F(field) - delta})
        Notification.objects.update(created_at=F('created_at') - delta)
        for state in self.svc.values():
            state['announced'] = [stamp - delta for stamp in state['announced']]
        # queued jobs keep the stamp they were made with, so they must be shifted too or they would look stale
        self.queue = [(sid, (datetime.fromisoformat(iso) - delta).isoformat()) for sid, iso in self.queue]

    # ── the notification job, with failures injected ─────────────────────────

    def run_job(self, args, fail_user=None, crash_on_call=None):
        calls = {'n': 0}
        attempted_failure = {'hit': False}
        real_notify = NotificationService.notify
        real_exists = Notification.exists_for_reference
        sid, stamp = args

        def spy_notify(user_id, **kwargs):
            service = self.db_service(kwargs['reference_id'])
            user = User.objects.select_related('artist_profile__approval_status').get(pk=user_id)
            profile = getattr(user, 'artist_profile', None)
            if user.role != 'artist' or not user.is_active or profile is None or profile.approval_status.name != 'approved':
                self.bad('I2', f'notified user {user_id} who is {user.role}/active={user.is_active}')
            if not (service.is_active and ServiceCategory.objects.get(pk=service.category_id).is_active):
                self.bad('I2', f'notified about service {service.pk} that is not live')
            if service.artists_announced_at is None or service.artists_announced_at.isoformat() != stamp:
                self.bad('I2', f'a job for an old announcement of service {service.pk} sent a notification')
            elif Notification.objects.filter(user_id=user_id, type=TYPE, reference_id=service.pk,
                                             created_at__gte=service.artists_announced_at).exists():
                self.bad('I2', f'user {user_id} already told about service {service.pk} in this announcement')
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
                patch('sunndari_apps.notifications.utils.NotificationFirebaseUtils.sync_notification'), \
                patch('sunndari_apps.notifications.utils.FirebaseUtils._ensure_initialized'), \
                patch('sunndari_apps.notifications.utils.messaging.send', return_value='m-1'):
            try:
                notify_artists_service_announced(sid, stamp)
                after = self.db_service(sid)
                current = after.artists_announced_at is not None and after.artists_announced_at.isoformat() == stamp
                if attempted_failure['hit'] and current and after.artists_notified_at is not None:
                    self.bad('I2', f'a recipient failed for service {sid} but the claim was not handed back, so nobody will retry')
            except Exception:
                if not crash_on_call:
                    raise
                after = self.db_service(sid)
                if after.artists_notified_at is not None and after.artists_announced_at.isoformat() == stamp:
                    self.bad('I2', f'a crashed job left service {sid} marked as notified')

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
            self.run_job(self.queue.pop(index), fail_user=self.rng.choice(list(self.artists)))
        else:
            self.run_job(self.queue.pop(index))

    def act_redispatch(self):
        with patch('sunndari_apps.core.tasks.notify_artists_service_announced.delay',
                   side_effect=lambda sid, iso: self.queue.append((sid, iso))):
            redispatch_unnotified_artist_announcements()

    # ── invariants ───────────────────────────────────────────────────────────

    def check(self):
        db = {s.pk: s for s in ServiceSubCategory.objects.select_related('category')}
        for sid, state in self.svc.items():
            if db[sid].is_active != state['active']:
                self.bad('model', f'service {sid} is_active={db[sid].is_active}, model says {state["active"]}')
            if not state['announced'] and any(self.announcement_state(sid)):
                self.bad('I3', f'service {sid} was never announced yet has announcement data')
        for note in Notification.objects.filter(type=TYPE).select_related('user'):
            if note.user.role != 'artist':
                self.bad('I5', f'a {note.user.role} has a service_activated notification')
            if not self.svc[note.reference_id]['announced']:
                self.bad('I3', f'service {note.reference_id} told someone without ever being announced')
        per_pair = {}
        for note in Notification.objects.filter(type=TYPE).order_by('created_at', 'pk'):
            per_pair.setdefault((note.user_id, note.reference_id), []).append(note.created_at)
        for (uid, sid), times in per_pair.items():
            history = sorted(self.svc[sid]['announced'])
            for earlier, later in zip(times, times[1:]):
                if not any(earlier < stamp <= later for stamp in history):
                    self.bad('I2', f'user {uid} told about service {sid} twice with no new announcement between')

    # ── the run ──────────────────────────────────────────────────────────────

    def simulate(self, seed):
        self.build_world(seed)
        actions = [(self.act_create_service, 4), (self.act_toggle_service, 12), (self.act_edit_service, 3),
                   (self.act_stale_copy_save, 2), (self.act_toggle_category, 3), (self.act_announce, 10),
                   (self.act_add_artist, 6), (self.act_add_non_artist, 2), (self.act_spoil_artist, 1),
                   (self.act_time_travel, 4), (self.act_job, 24), (self.act_redispatch, 3)]
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
        for name, minimum in (('switched on', 8), ('announcements', 8), ('announcements refused', 1), ('jobs lost', 1),
                              ('jobs delivered twice', 1), ('jobs crashed', 1), ('jobs with a failing recipient', 1),
                              ('notifications made', 15)):
            self.assertGreaterEqual(self.tally[name], minimum, f'seed {seed}: too little coverage of {name!r}: {dict(self.tally)}')
        print('SIM_COVERAGE', seed, dict(self.tally))

    def check_eventual_delivery(self):
        """I6: after lost jobs are re-dispatched and everything is allowed to run, nothing recent is left half-done."""
        now = timezone.now()
        young = [s for s in ServiceSubCategory.objects.select_related('category')
                 if s.is_active and s.category.is_active and s.artists_announced_at and s.artists_announced_at > now - timedelta(hours=20)]
        for _ in range(8):
            self.shift(timedelta(minutes=3))
            self.act_redispatch()
            if not self.queue:
                break
            while self.queue:
                self.run_job(self.queue.pop(0))
        for service in young:
            service.refresh_from_db()
            if service.artists_notified_at is None:
                self.bad('I6', f'recent live announcement of service {service.pk} was never sent')
                continue
            announce_op = self.svc[service.pk]['announce_op']
            for uid, info in self.artists.items():
                count = Notification.objects.filter(user_id=uid, type=TYPE, reference_id=service.pk,
                                                    created_at__gte=service.artists_announced_at).count()
                if info['born'] < announce_op and not info['ever_ineligible'] and count != 1:
                    self.bad('I6', f'artist {uid} has {count} notifications for service {service.pk} (expected exactly 1)')
                if count > 1:
                    self.bad('I6', f'artist {uid} has {count} notifications for service {service.pk}')

    def test_seed_1(self):
        self.simulate(20261024)

    def test_seed_2(self):
        self.simulate(7)

    def test_seed_3(self):
        self.simulate(424242)
