from django.core.management.base import BaseCommand

from sunndari_apps.authentication.models import User


class Command(BaseCommand):
    help = (
        'Invalidates every stored access/refresh token so all users must log in again. '
        'Run once after deploying the profile token-leak fix (tokens may already have been exposed).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Required: confirm you really want to log everyone out.')

    def handle(self, *args, **options):
        if not options['yes']:
            self.stderr.write('Refusing to run without --yes (this logs every user out).')
            return
        revoked = User.objects.exclude(access_token='', refresh_token='').update(access_token='', refresh_token='')
        self.stdout.write(f'Revoked sessions for {revoked} users.')
