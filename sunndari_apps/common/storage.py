import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """Storage for files that must never be reachable by URL (e.g. KYC documents).

    Lives under settings.PRIVATE_MEDIA_ROOT — outside MEDIA_ROOT, so the public
    MEDIA_URL route can never serve it — and has no base_url, so `.url` raises instead
    of silently producing a link. The only way to read a file is to open it inside an
    authenticated, authorised view."""

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None
