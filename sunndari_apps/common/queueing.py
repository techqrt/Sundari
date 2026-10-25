import logging

logger = logging.getLogger(__name__)


def enqueue(task, *args) -> bool:
    """Queues a Celery task without ever raising or hanging, for work that happens after a business action has already
    been saved (a notification, an email). Returns whether it was queued.

    It uses a dedicated connection with one quick attempt: going through Celery's shared pool waits about 19 seconds
    when the broker is down, which would hang the request that triggered the work. A failure is logged and the caller
    carries on; whatever was saved stays saved, and periodic jobs pick up anything that was missed."""
    try:
        from sunndari.celery import app
        with app.connection_for_write() as connection:
            connection.ensure_connection(max_retries=1, interval_start=0, interval_step=0, interval_max=0)
            task.apply_async(args=list(args), connection=connection, retry=False)
        return True
    except Exception:
        logger.exception('Could not queue %s', getattr(task, 'name', task))
        return False
