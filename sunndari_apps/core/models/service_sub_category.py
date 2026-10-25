import logging
from datetime import timedelta

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from sunndari.constants import Constants

logger = logging.getLogger(__name__)


class ServiceSubCategory(models.Model):
    sub_category_id = models.AutoField(primary_key=True)
    category = models.ForeignKey(
        'core.ServiceCategory',
        on_delete=models.CASCADE,
        related_name='sub_categories',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # When the service last went live. Set only by save() on a real inactive -> active change (or when a service
    # is created active), never by hand: that is what makes the "activated in the last 15 days" window
    # trustworthy. NULL means it was live before activation was tracked, so it is never counted as new.
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Set once the "now available" notification for the current activation has been sent (see core/tasks.py);
    # cleared on every new activation. Lets a retried or duplicated send be recognised and skipped.
    activation_notified_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'service_sub_categories'
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} → {self.name}"

    def save(self, *args, **kwargs):
        """Stamps activated_at whenever the service genuinely goes from inactive to active (or is created
        active). The previous state is read from the database under a row lock rather than trusted from this
        instance, so a stale copy (an admin form left open) or two simultaneous saves cannot activate twice or
        restart the 15-day window. Saving an already-active service, editing other fields, or deactivating
        leaves the timestamps alone. Bulk operations that skip save() (queryset.update, bulk_create) also skip
        this rule, so activate through save()."""
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'is_active' not in update_fields:
            return super().save(*args, **kwargs)
        activated_now = False
        with transaction.atomic():
            current = None
            if not self._state.adding and self.pk is not None:
                current = ServiceSubCategory.objects.select_for_update().filter(pk=self.pk).values(
                    'is_active', 'activated_at', 'activation_notified_at').first()
            if self.is_active and not (current and current['is_active']):
                self.activated_at = timezone.now()
                self.activation_notified_at = None
                if update_fields is not None:
                    kwargs['update_fields'] = list(update_fields) + ['activated_at', 'activation_notified_at']
                activated_now = True
            elif current:
                # Not an activation: this copy may be stale, so it must not write its old timestamps over
                # the database's (including the notification mark another process may just have set).
                self.activated_at = current['activated_at']
                self.activation_notified_at = current['activation_notified_at']
            saved = super().save(*args, **kwargs)
            if activated_now:
                # Only after the activation is committed: a rolled-back save must announce nothing, and the
                # task must find the committed row. Never part of the save's outcome (see _dispatch).
                pk, stamp = self.pk, self.activated_at
                transaction.on_commit(lambda: ServiceSubCategory._dispatch_activation_notice(pk, stamp))
            return saved

    @staticmethod
    def _dispatch_activation_notice(sub_category_id: int, activated_at) -> None:
        """Queues the "new service" notification. A broker that is down must not undo or fail an activation
        that has already been saved: enqueue() logs it, and the periodic redispatch job picks the service up."""
        from sunndari_apps.common.queueing import enqueue
        from sunndari_apps.core.tasks import notify_service_activated
        enqueue(notify_service_activated, sub_category_id, activated_at.isoformat())

    @staticmethod
    def claim_activation_notification(sub_category_id: int, activated_at):
        """Atomically takes the right to notify for ONE activation: succeeds only while this exact activation is
        still current, the service is still live, and nobody has notified for it yet. Returns the claim time, or
        None. Two workers (a duplicate task, a retry racing the original) cannot both win."""
        claimed_at = timezone.now()
        won = ServiceSubCategory.objects.filter(
            pk=sub_category_id, activated_at=activated_at, activation_notified_at__isnull=True,
            **ServiceSubCategory.live_filter(),
        ).update(activation_notified_at=claimed_at)
        return claimed_at if won else None

    @staticmethod
    def release_activation_notification(sub_category_id: int, claimed_at) -> None:
        """Gives the claim back (only if it is still ours) so a retry or the redispatch job can finish the job."""
        ServiceSubCategory.objects.filter(pk=sub_category_id, activation_notified_at=claimed_at).update(
            activation_notified_at=None)

    # ── "live" = what customers and artists may use ───────────────────────────
    # A service is live when it AND its parent category are active. Turning one service off never turns its
    # parent off (the category still has its other services); a category switched off hides its services
    # without any of them being edited.

    @staticmethod
    def live_filter(prefix: str = '') -> dict:
        """Query lookups that keep only live services. `prefix` is the path from the model being queried to
        the sub-category, e.g. live_filter('sub_category__') on PricingPackage or live_filter() on this model."""
        return {f'{prefix}is_active': True, f'{prefix}category__is_active': True}

    @staticmethod
    def assert_live(sub_category_ids) -> None:
        """Raises (HTTP 400, like every other refusal here) unless every given service is live. Used wherever
        something NEW is attached to a service; existing rows and bookings are never re-checked."""
        wanted = {sub_category_id for sub_category_id in sub_category_ids if sub_category_id is not None}
        if not wanted:
            return
        live = ServiceSubCategory.objects.filter(
            sub_category_id__in=wanted, **ServiceSubCategory.live_filter(),
        ).count()
        if live != len(wanted):
            raise ValueError(Constants.service_unavailable)

    @staticmethod
    def get_recently_activated(days: int, now=None) -> list:
        """Live services that went live within the last `days` days, newest first. Measured against the server
        clock (never a device's). A service switched off since, one whose category is off, one activated before
        activation was tracked (NULL) and one dated in the future are all left out. Switching a service off and
        on again gives it a new activated_at, so it qualifies again."""
        now = now or timezone.now()
        return list(ServiceSubCategory.objects.filter(
            activated_at__gt=now - timedelta(days=days), activated_at__lte=now, **ServiceSubCategory.live_filter(),
        ).order_by('-activated_at', 'sub_category_id').values(
            'sub_category_id', 'name', 'description', 'category_id', 'category__name', 'activated_at',
        ))

    @staticmethod
    def get(sub_category_id: int) -> dict:
        return ServiceSubCategory.objects.filter(sub_category_id=sub_category_id).values(
            'sub_category_id', 'category_id', 'category__name', 'name', 'description', 'is_active', 'created_at', 'updated_at'
        ).first()

    @staticmethod
    def get_all(
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
        only_live: bool = False,
    ) -> list:
        data = ServiceSubCategory.objects.all()
        if only_live:
            data = data.filter(**ServiceSubCategory.live_filter())
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(name__icontains=search_key) | Q(description__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'sub_category_id', 'category_id', 'category__name', 'name', 'description', 'is_active', 'created_at', 'updated_at'
        ))
