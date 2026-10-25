from django.core.management.base import BaseCommand

from sunndari_apps.payments.models import Payment


class Command(BaseCommand):
    help = (
        "Retries every refund still owed to a customer (a cancelled or missed booking's payment, or a gateway "
        "capture that could not be applied), ignoring the automatic backoff. The same work runs on a schedule "
        "(payments.tasks.retry_owed_refunds); this is for running it by hand. Safe to re-run."
    )

    def handle(self, *args, **options):
        totals = Payment.retry_owed_refunds(force=True)
        self.stdout.write(f"refunded={totals['refunded']} still_pending={totals['pending']}")
