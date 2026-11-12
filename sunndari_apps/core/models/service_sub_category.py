import logging
from datetime import timedelta

from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from sunndari.constants import Constants

logger = logging.getLogger(__name__)

# Longest wording an admin may send to artists (it is also what a push shows, so it has to stay short).
ANNOUNCEMENT_MESSAGE_MAX = 300


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
    # The artist announcement: an admin explicitly telling artists this service is open for them to add. Nothing here
    # is set by creating, activating or editing a service; only announce_to_artists() sets it, and only when an admin
    # asks for it. Never set by hand (like activated_at, so it can be trusted).
    #   artists_announced_at: when the admin last announced it (each announcement, including a re-send, is new);
    #   artists_notified_at: the claim a notification job takes for the current announcement, so a retried or
    #       duplicated job sends nothing twice;
    #   artists_announcement_message: the exact wording, kept so a retry sends the same text.
    artists_announced_at = models.DateTimeField(null=True, blank=True, editable=False)
    artists_notified_at = models.DateTimeField(null=True, blank=True, editable=False)
    artists_announcement_message = models.TextField(null=True, blank=True, editable=False)
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
        with transaction.atomic():
            current = None
            if not self._state.adding and self.pk is not None:
                current = ServiceSubCategory.objects.select_for_update().filter(pk=self.pk).values(
                    'is_active', 'activated_at',
                    'artists_announced_at', 'artists_notified_at', 'artists_announcement_message').first()
            if self.is_active and not (current and current['is_active']):
                self.activated_at = timezone.now()
                if update_fields is not None:
                    kwargs['update_fields'] = list(update_fields) + ['activated_at']
            elif current:
                # Not an activation: this copy may be stale, so it must not write its old timestamp over the database's.
                self.activated_at = current['activated_at']
            if current:
                # The announcement is never touched by a save (activating, deactivating or editing included), and a
                # stale copy must not write its old values over the database's. Saving never notifies anyone either:
                # telling artists is a separate, explicit admin action (announce_to_artists + dispatch_artist_announcement).
                self.artists_announced_at = current['artists_announced_at']
                self.artists_notified_at = current['artists_notified_at']
                self.artists_announcement_message = current['artists_announcement_message']
            return super().save(*args, **kwargs)

    # ── announcing a service to artists (explicit, admin-initiated) ───────────────────────────────────

    @staticmethod
    def default_announcement_message(name: str) -> str:
        return f'{name} is now available. Add it to your services to start getting bookings.'

    @staticmethod
    def announce_to_artists(sub_category_id: int, message: str = None):
        """Records that an admin announced this service to artists, and returns the announcement time. Only the admin
        action calls this; nothing else does, so creating, activating or editing a service never announces anything.

        The service must be live (it and its category active): artists can only add a live service, so announcing
        a hidden one would send them to something they cannot add. `message` is the wording artists will read; blank
        means the standard text. Announcing again is allowed and starts a fresh announcement (new time, claim cleared),
        which is how an admin re-sends. This records the announcement only; sending is a separate step."""
        message = (message or '').strip()
        if len(message) > ANNOUNCEMENT_MESSAGE_MAX:
            raise ValueError(Constants.announcement_message_too_long)
        with transaction.atomic():
            service = ServiceSubCategory.objects.select_for_update().select_related('category').filter(pk=sub_category_id).first()
            if service is None:
                raise ValueError(Constants.data_no_match)
            if not (service.is_active and service.category.is_active):
                raise ValueError(Constants.service_announce_inactive)
            announced_at = timezone.now()
            # update(), not save(): the save() rule is about activation and must not run for an announcement.
            ServiceSubCategory.objects.filter(pk=sub_category_id).update(
                artists_announced_at=announced_at, artists_notified_at=None,
                artists_announcement_message=message or ServiceSubCategory.default_announcement_message(service.name),
            )
        return announced_at

    @staticmethod
    def dispatch_artist_announcement(sub_category_id: int, announced_at) -> bool:
        """Queues the job that notifies artists about one announcement; returns whether it was queued. The admin action
        calls it after the announcement is committed (never from a save). A broker that is down does not undo or fail the
        announcement: enqueue() logs it and the periodic redispatch job picks it up."""
        from sunndari_apps.common.queueing import enqueue
        from sunndari_apps.core.tasks import notify_artists_service_announced
        return enqueue(notify_artists_service_announced, sub_category_id, announced_at.isoformat())

    @staticmethod
    def claim_artist_announcement(sub_category_id: int, announced_at):
        """Atomically takes the right to notify artists for ONE announcement: succeeds only while that exact announcement
        is current, the service is still live, and nobody has notified for it yet. Returns the claim time, or None. Two
        workers (a duplicate job, a retry racing the original) cannot both win."""
        claimed_at = timezone.now()
        won = ServiceSubCategory.objects.filter(
            pk=sub_category_id, artists_announced_at=announced_at, artists_notified_at__isnull=True,
            **ServiceSubCategory.live_filter(),
        ).update(artists_notified_at=claimed_at)
        return claimed_at if won else None

    @staticmethod
    def release_artist_announcement(sub_category_id: int, claimed_at) -> None:
        """Gives the claim back (only if it is still ours) so a retry can finish the job."""
        ServiceSubCategory.objects.filter(pk=sub_category_id, artists_notified_at=claimed_at).update(artists_notified_at=None)

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
    def bookable_filter() -> Q:
        """Keeps only services a customer could book right now: live (see live_filter) AND at least one active package
        under it belongs to an artist customers can see: approved, registration payment settled (or exempt) and bookings
        ON (ArtistProfile.public_filter, the same test customer search uses). A service nobody has added packages for
        yet, or whose artists are pending, suspended, unpaid, not accepting bookings or have switched the packages off,
        is not bookable, so customers do not see it. Used in an Exists, so a service with
        many packages or artists still appears once."""
        from sunndari_apps.artists.models import ArtistProfile, PricingPackage
        has_package = Exists(PricingPackage.objects.filter(
            ArtistProfile.public_filter('artist__'), sub_category=OuterRef('pk'), is_active=True,
        ))
        return Q(has_package, **ServiceSubCategory.live_filter())

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
    def get_announced_for_artist(artist_id: int, days: int, now=None) -> list:
        """Live services an admin announced to artists within the last `days` days that this artist has not added yet,
        newest announcement first. Measured against the server clock (never a device's). "Added" means the artist has an
        active offering for the service or an active package under it. A service switched off since, one whose category is
        off, one never announced and one dated in the future are left out. Announcing again gives a new time, so a service
        the artist still has not added is shown again."""
        from sunndari_apps.artists.models import ArtistServiceOffering, PricingPackage
        now = now or timezone.now()
        added = ServiceSubCategory.objects.filter(
            Q(pk__in=ArtistServiceOffering.objects.filter(artist_id=artist_id, is_active=True).values('sub_category_id'))
            | Q(pk__in=PricingPackage.objects.filter(artist_id=artist_id, is_active=True).values('sub_category_id'))
        ).values('pk')
        return list(ServiceSubCategory.objects.filter(
            artists_announced_at__gt=now - timedelta(days=days), artists_announced_at__lte=now,
            **ServiceSubCategory.live_filter(),
        ).exclude(pk__in=added).order_by('-artists_announced_at', 'sub_category_id').values(
            'sub_category_id', 'name', 'description', 'category_id', 'category__name',
            'artists_announced_at', 'artists_announcement_message',
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
        only_bookable: bool = False,
    ) -> list:
        data = ServiceSubCategory.objects.all()
        if only_bookable:
            data = data.filter(ServiceSubCategory.bookable_filter())
        elif only_live:
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
