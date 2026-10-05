from django.core.management.base import BaseCommand

from sunndari_apps.core.models.payment_status import PaymentStatus
from sunndari_apps.payments.models import Payment


class Command(BaseCommand):
    help = (
        "Retries gateway refunds for payments that are still 'paid' although their booking was "
        "cancelled or missed (the first attempt failed — see Payment.mark_refunded). Safe to re-run."
    )

    def handle(self, *args, **options):
        refunded_status = PaymentStatus.objects.get(name='refunded')
        booking_ids = (
            Payment.objects.filter(status__name='paid', booking__status__name__in=['cancelled', 'no_show'])
            .values_list('booking_id', flat=True).distinct()
        )
        totals = {'refunded': 0, 'pending': 0}
        for booking_id in booking_ids:
            outcome = Payment.mark_refunded(booking_id=booking_id, status_id=refunded_status.status_id)
            for key in totals:
                totals[key] += outcome[key]
        self.stdout.write(f"refunded={totals['refunded']} still_pending={totals['pending']}")
