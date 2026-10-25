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

NOTIFICATION_TYPE = 'service_activated'


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_service_activated(self, sub_category_id: int, activated_at: str) -> dict:
    """Tells every active customer that a service is now available. Queued when an admin switches a service on
    (ServiceSubCategory.save), after the activation is committed.

    Safe to run twice, concurrently, or after a crash:
      * the activation is claimed atomically first, so a duplicate task does nothing;
      * each customer is checked for an existing notification about this activation, so a retry never
        notifies the same person twice;
      * if anything fails (an error here, or a customer who could not be notified) the claim is handed back so
        the retry / the redispatch job finishes only what is missing.
    A notification problem never affects the service's active status; it is already saved.
    Only customers are told (artists are not part of this announcement)."""
    activated = datetime.fromisoformat(activated_at)
    claimed_at = ServiceSubCategory.claim_activation_notification(sub_category_id, activated)
    if claimed_at is None:
        return {'sent': 0, 'skipped': 0, 'failed': 0, 'note': 'not current, not live, or already notified'}

    service = ServiceSubCategory.objects.select_related('category').get(pk=sub_category_id)
    title = 'New service available'
    message = f'{service.name} ({service.category.name}) is now available. Find an artist and book today!'
    sent = skipped = failed = 0
    try:
        for user_id in User.objects.filter(role='customer', is_active=True).values_list('user_id', flat=True).iterator(chunk_size=500):
            if Notification.exists_for_reference(user_id, NOTIFICATION_TYPE, sub_category_id, since=activated):
                skipped += 1
                continue
            if NotificationService.notify(
                user_id=user_id, title=title, message=message, type=NOTIFICATION_TYPE, reference_id=sub_category_id,
            ) is None:
                failed += 1
                continue
            sent += 1
    except Exception as error:
        ServiceSubCategory.release_activation_notification(sub_category_id, claimed_at)
        raise self.retry(exc=error)
    if failed:
        logger.warning('Service %s activation: %s customer(s) could not be notified; will be retried', sub_category_id, failed)
        ServiceSubCategory.release_activation_notification(sub_category_id, claimed_at)
    return {'sent': sent, 'skipped': skipped, 'failed': failed}


@shared_task
def redispatch_unnotified_service_activations() -> int:
    """Runs every few minutes (see CELERY_BEAT_SCHEDULE). The safety net for the queue itself: an activation whose
    task was never queued (broker down), lost (worker killed) or left unfinished (a recipient failed) is queued
    again. Only recent activations, and not the last couple of minutes (those are still being sent). The
    notify task's claim makes a redundant dispatch harmless. Returns how many it queued."""
    now = timezone.now()
    pending = ServiceSubCategory.objects.filter(
        activation_notified_at__isnull=True,
        activated_at__gt=now - timedelta(hours=Configurations.service_notify_redispatch_hours),
        activated_at__lte=now - timedelta(minutes=2),
        **ServiceSubCategory.live_filter(),
    ).values_list('pk', 'activated_at')
    queued = 0
    for sub_category_id, activated_at in pending:
        notify_service_activated.delay(sub_category_id, activated_at.isoformat())
        queued += 1
    return queued
