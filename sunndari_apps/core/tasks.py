import logging
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone

from sunndari.config import Configurations
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.notifications.utils import NotificationService

logger = logging.getLogger(__name__)

# The notification type keeps the name the apps already know; it now means "a service is open for you to add".
NOTIFICATION_TYPE = 'service_activated'


def eligible_artist_user_ids():
    """The artists an announcement goes to: active accounts whose profile is approved. Artists still being reviewed,
    rejected or suspended are left out (they cannot take bookings), and so is everyone who is not an artist."""
    return User.objects.filter(
        role='artist', is_active=True, artist_profile__approval_status__name='approved',
    ).values_list('user_id', flat=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_artists_service_announced(self, sub_category_id: int, announced_at: str) -> dict:
    """Tells every eligible artist that a service is open for them to add. Queued only by the admin's explicit
    "notify artists" action, never by creating, activating or editing a service. It only notifies: it never adds the
    service to anyone, which stays the artist's own choice.

    Safe to run twice, concurrently, or after a crash:
      * the announcement is claimed atomically first, so a duplicate job does nothing;
      * each artist is checked for an existing notification about this announcement, so a retry never notifies the
        same person twice;
      * if anything fails (an error here, or an artist who could not be notified) the claim is handed back so the retry
        / the redispatch job finishes only what is missing.
    A notification problem never affects the service; it was saved already."""
    announced = datetime.fromisoformat(announced_at)
    claimed_at = ServiceSubCategory.claim_artist_announcement(sub_category_id, announced)
    if claimed_at is None:
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'note': 'not current, not live, or already notified'}

    service = ServiceSubCategory.objects.get(pk=sub_category_id)
    title = f'New service: {service.name}'
    message = service.artists_announcement_message or ServiceSubCategory.default_announcement_message(service.name)
    sent = skipped = failed = 0
    try:
        for user_id in eligible_artist_user_ids().iterator(chunk_size=500):
            if Notification.exists_for_reference(user_id, NOTIFICATION_TYPE, sub_category_id, since=announced):
                skipped += 1
                continue
            if NotificationService.notify(
                user_id=user_id, title=title, message=message, type=NOTIFICATION_TYPE, reference_id=sub_category_id,
            ) is None:
                failed += 1
                continue
            sent += 1
    except Exception as error:
        ServiceSubCategory.release_artist_announcement(sub_category_id, claimed_at)
        raise self.retry(exc=error)
    if failed:
        logger.warning('Service %s announcement: %s artist(s) could not be notified; will be retried', sub_category_id, failed)
        ServiceSubCategory.release_artist_announcement(sub_category_id, claimed_at)
    return {'sent': sent, 'skipped': skipped, 'failed': failed}


@shared_task
def redispatch_unnotified_artist_announcements() -> int:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). The safety net for the queue itself: an announcement whose job
    was never queued (broker down), lost (worker killed) or left unfinished (an artist failed) is queued again. Only
    recent announcements, and not the last couple of minutes (those are still being sent). The job's claim makes a
    redundant dispatch harmless. Returns how many it queued."""
    now = timezone.now()
    pending = ServiceSubCategory.objects.filter(
        artists_notified_at__isnull=True,
        artists_announced_at__gt=now - timedelta(hours=Configurations.service_notify_redispatch_hours),
        artists_announced_at__lte=now - timedelta(minutes=2),
        **ServiceSubCategory.live_filter(),
    ).values_list('pk', 'artists_announced_at')
    queued = 0
    for sub_category_id, announced_at in pending:
        notify_artists_service_announced.delay(sub_category_id, announced_at.isoformat())
        queued += 1
    return queued
