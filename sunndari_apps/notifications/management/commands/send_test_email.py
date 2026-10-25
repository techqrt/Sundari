from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sunndari_apps.common.emailing import EmailDeliveryError, BRAND, notification_message, send_email


class Command(BaseCommand):
    help = (
        'Sends ONE real test email through the configured SMTP relay (Brevo) to the address you give, to prove the '
        'credentials, the sender address and delivery all work. Prints only the outcome, never a credential.'
    )

    def add_arguments(self, parser):
        parser.add_argument('to', help='Where to send the test email, e.g. you@example.com')

    def handle(self, *args, **options):
        to = options['to']
        if '@' not in to:
            raise CommandError('Give a full email address.')
        self.stdout.write(
            f'Sending via {settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
            f'(TLS={settings.EMAIL_USE_TLS}) from {settings.DEFAULT_FROM_EMAIL} ...'
        )
        subject, text, page = notification_message(
            f'{BRAND} email is working',
            'This is a test message from your SUNNDARI server. If you can read it, sign-in codes and account '
            'notifications will reach your users.',
        )
        try:
            send_email(to=to, subject=subject, text=text, html_body=page, tag='test')
        except EmailDeliveryError:
            raise CommandError(
                'The mail server did not accept the message. Check the SMTP login/key, that DEFAULT_FROM_EMAIL is a '
                'verified sender in Brevo, and the server log for the reason.'
            )
        self.stdout.write(self.style.SUCCESS(f'Accepted by the mail server for {to}. Check the inbox (and spam).'))
