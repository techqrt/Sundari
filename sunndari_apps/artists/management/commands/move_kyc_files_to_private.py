import os
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand

from sunndari_apps.artists.models.document import ArtistDocument


class Command(BaseCommand):
    help = (
        'One-off: move already-uploaded KYC documents from the public MEDIA_ROOT into '
        'PRIVATE_MEDIA_ROOT (where ArtistDocument.file now lives). Safe to re-run; '
        'use --dry-run to preview.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        moved = already_private = missing = 0
        for document in ArtistDocument.objects.exclude(file=''):
            name = document.file.name
            private_path = os.path.join(settings.PRIVATE_MEDIA_ROOT, name)
            public_path = os.path.join(settings.MEDIA_ROOT, name)
            if os.path.exists(private_path):
                already_private += 1
                continue
            if not os.path.exists(public_path):
                missing += 1
                self.stderr.write(f'Document #{document.document_id}: file not found at {public_path}')
                continue
            moved += 1
            if dry_run:
                self.stdout.write(f'[dry-run] would move {public_path} -> {private_path}')
                continue
            os.makedirs(os.path.dirname(private_path), exist_ok=True)
            shutil.move(public_path, private_path)
        self.stdout.write(
            f'moved={moved} already_private={already_private} missing={missing}'
            + (' (dry run)' if dry_run else '')
        )
