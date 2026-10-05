from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.crypto import decrypt_text
from sunndari_apps.authentication.models import User
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.document import ArtistDocument
from sunndari_apps.core.models.approval_status import ApprovalStatus
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.admin_panel.serializers.response.get_all.get_all_artist_document import (
    AdminArtistDocumentResponseSerializer,
)
from sunndari.constants import Constants


class AdminArtistDocumentView:
    def __init__(self):
        self.data_get = Constants.data_get

    def _require_admin(self, user_id: int) -> None:
        user = User.get(user_id=user_id)
        if not user or user['role'] != 'admin':
            raise ValueError(Constants.forbidden_resource)

    @Common(response_handler=AdminArtistDocumentResponseSerializer).exception_handler
    def get_all_extract(self, params):
        self._require_admin(user_id=params.user_id)
        if not ArtistProfile.objects.filter(artist_id=params.artist_id).exists():
            raise ValueError(Constants.artist_not_found)
        data = []
        for document in ArtistDocument.objects.filter(artist_id=params.artist_id).select_related(
            'verification_status',
        ).order_by('-created_at'):
            base = f'/artists/documents/file/?document_id={document.document_id}'
            data.append({
                'documentId': document.document_id,
                'artistId': document.artist_id,
                'documentType': document.document_type,
                'idType': document.id_type,
                'documentNumber': document.document_number,
                # Full ID number for admin verification (Aadhaar is never stored in full,
                # so for it this is the same masked value).
                'idNumber': decrypt_text(document.document_number_encrypted) or document.document_number,
                'fileUrl': base,
                'backFileUrl': f'{base}&side=back' if document.back_file else None,
                'verificationStatus': document.verification_status.name if document.verification_status else None,
                'rejectionReason': document.rejection_reason,
                'createdAt': document.created_at,
            })
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common().exception_handler
    def verify_extract(self, params):
        with transaction.atomic():
            self._require_admin(user_id=params.user_id)
            document = ArtistDocument.objects.select_for_update().select_related(
                'artist', 'verification_status',
            ).filter(document_id=params.document_id).first()
            if not document:
                raise ValueError(Constants.data_no_match)
            if document.verification_status and document.verification_status.name != 'pending':
                raise ValueError(Constants.document_already_decided)
            decided = ApprovalStatus.objects.filter(name=params.decision).first()
            if not decided:
                raise ValueError(f"Approval status '{params.decision}' is not configured")
            document.verification_status = decided
            document.rejection_reason = params.reason or None if params.decision == 'rejected' else None
            document.save()
            if params.decision == 'approved':
                title, message = 'Document verified', 'Your identity document has been verified.'
            else:
                title = 'Document rejected'
                message = f'Your document was rejected: {params.reason}'
            NotificationService.notify(
                user_id=document.artist.user_id, title=title, message=message,
                type=f'document_{params.decision}',
            )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=f'Document {params.decision}')
        )
