import os
import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from sunndari_apps.common.storage import PrivateMediaStorage


def artist_document_upload_path(instance, filename):
    # Random name: never trust or expose the client's file name.
    extension = os.path.splitext(filename)[1].lower()
    return f'artist_documents/artist_{instance.artist_id}/{uuid.uuid4().hex}{extension}'


def artist_document_back_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f'artist_documents/artist_{instance.artist_id}/{uuid.uuid4().hex}_back{extension}'


class ArtistDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('id_proof', 'ID Proof'),
        ('address_proof', 'Address Proof'),
        ('certification', 'Professional Certification'),
    ]

    ID_TYPE_CHOICES = [
        ('aadhaar', 'Aadhaar'),
        ('voter_id', 'Voter ID'),
        ('passport', 'Passport'),
        ('driving_licence', 'Driving Licence'),
    ]

    document_id = models.AutoField(primary_key=True)
    artist = models.ForeignKey(
        'artists.ArtistProfile',
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    # Only meaningful for document_type='id_proof' (null on legacy rows and other types).
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, null=True, blank=True)
    # Display value: masked for ID proofs (only the last 4 characters are ever shown).
    document_number = models.CharField(max_length=100, null=True, blank=True)
    # Full ID number, encrypted at rest — stored for every ID type except Aadhaar, for which
    # only the masked last 4 digits are ever kept. Readable by admin review only.
    document_number_encrypted = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to=artist_document_upload_path, storage=PrivateMediaStorage())
    back_file = models.FileField(
        upload_to=artist_document_back_upload_path, storage=PrivateMediaStorage(), null=True, blank=True,
    )
    verification_status = models.ForeignKey(
        'core.ApprovalStatus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'artist_documents'

    def __str__(self):
        return f"{self.document_type} (Artist #{self.artist_id})"

    def create(
        self,
        artist_id: int,
        document_type: str,
        file,
        document_number: str = None,
        id_type: str = None,
        back_file=None,
        document_number_encrypted: str = None,
    ) -> int:
        from sunndari_apps.core.models.approval_status import ApprovalStatus
        pending = ApprovalStatus.objects.filter(name='pending').first()
        self.artist_id = artist_id
        self.document_type = document_type
        self.id_type = id_type
        self.document_number = document_number
        self.document_number_encrypted = document_number_encrypted
        self.file = file
        if back_file:
            self.back_file = back_file
        self.verification_status = pending
        self.save()
        return self.document_id

    @staticmethod
    def remove(document_id: int) -> None:
        document = ArtistDocument.objects.get(document_id=document_id)
        ArtistDocument._delete_with_files(document)

    @staticmethod
    def _delete_with_files(document: 'ArtistDocument') -> None:
        # The row owns its stored files — don't leave identity documents orphaned on disk.
        for stored in (document.file, document.back_file):
            if stored:
                stored.delete(save=False)
        document.delete()

    @staticmethod
    def get(document_id: int) -> dict:
        return ArtistDocument.objects.filter(document_id=document_id).values(
            'document_id', 'artist_id', 'document_type', 'id_type', 'document_number', 'file', 'back_file',
            'verification_status_id', 'rejection_reason', 'created_at', 'updated_at',
        ).first()

    @staticmethod
    def get_all(
        artist_id: int,
        sort_by: str = '',
        sort_order: str = 'asc',
        filter_key: str = '',
        filter_value: str = '',
        search_key: str = '',
    ) -> list:
        data = ArtistDocument.objects.filter(artist_id=artist_id)
        if filter_key and filter_value:
            lookup = '__exact' if filter_value.isdigit() else '__icontains'
            data = data.filter(**{f'{filter_key}{lookup}': filter_value})
        if search_key:
            data = data.filter(Q(document_type__icontains=search_key) | Q(document_number__icontains=search_key))
        if sort_by:
            data = data.order_by(('-' if sort_order == 'desc' else '') + sort_by)
        return list(data.values(
            'document_id', 'artist_id', 'document_type', 'id_type', 'document_number', 'file', 'back_file',
            'verification_status_id', 'rejection_reason', 'created_at', 'updated_at',
        ))

    @staticmethod
    def replace_id_proofs(artist_id: int, keep_document_id: int) -> None:
        """An artist has exactly one ID proof: submitting a new one supersedes (and deletes,
        files included) every earlier one."""
        for old in ArtistDocument.objects.filter(artist_id=artist_id, document_type='id_proof').exclude(
            document_id=keep_document_id,
        ):
            ArtistDocument._delete_with_files(old)

    @staticmethod
    def has_type(artist_id: int, document_type: str) -> bool:
        return ArtistDocument.objects.filter(artist_id=artist_id, document_type=document_type).exists()
