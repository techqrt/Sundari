import json
import os
from django.db import transaction
from django.http import FileResponse
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.uploads import validate_image_or_pdf, SAFE_CONTENT_TYPES
from sunndari_apps.common.crypto import encrypt_text
from sunndari_apps.artists.kyc import BACK_IMAGE_REQUIRED, mask_number
from sunndari_apps.authentication.models import User
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.document import ArtistDocument
from sunndari_apps.artists.serializers.response.get.get_document import DocumentResponseSerializer
from sunndari_apps.artists.serializers.response.get_all.get_all_document import DocumentResponseGetAllSerializer
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class ArtistDocumentView:
    def __init__(self):
        self.data_get = Constants.data_get
        self.data_no_match = Constants.data_no_match

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @staticmethod
    def _with_file_url(rows: list) -> list:
        # KYC files are never exposed by storage path or public URL: 'file' is replaced by
        # the authenticated download route, which checks owner-or-admin on every request.
        for row in rows:
            base = f"/artists/documents/file/?document_id={row['document_id']}"
            row['file'] = base
            row['back_file'] = f'{base}&side=back' if row.get('back_file') else None
        return rows

    @Common().exception_handler
    def create_extract(self, params, file, back_file=None):
        if not file:
            raise ValueError(Constants.file_required)
        validate_image_or_pdf(file)
        is_id_proof = params.document_type == 'id_proof'
        if back_file:
            if not is_id_proof:
                raise ValueError(Constants.kyc_id_type_not_allowed)
            validate_image_or_pdf(back_file)
        if is_id_proof and params.id_type in BACK_IMAGE_REQUIRED and not back_file:
            raise ValueError(Constants.kyc_back_required)

        display_number = params.document_number
        encrypted_number = None
        if is_id_proof:
            # Only a masked value is ever shown; the full number is kept (encrypted) for
            # admin verification — except Aadhaar, where just the last 4 digits are retained.
            display_number = mask_number(params.document_number)
            if params.id_type != 'aadhaar':
                encrypted_number = encrypt_text(params.document_number)
        obj = ArtistDocument()
        try:
            with transaction.atomic():
                profile = self._get_profile(user_id=params.user_id)
                document_id = obj.create(
                    artist_id=profile.artist_id,
                    document_type=params.document_type,
                    file=file,
                    document_number=display_number or None,
                    id_type=params.id_type if is_id_proof else None,
                    back_file=back_file,
                    document_number_encrypted=encrypted_number,
                )
                if is_id_proof:
                    ArtistDocument.replace_id_proofs(artist_id=profile.artist_id, keep_document_id=document_id)
        except Exception:
            # The files are written when the row is saved; the rollback removes the row but not
            # the stored identity documents, so remove them here rather than leave orphans.
            for stored in (obj.file, obj.back_file):
                if stored:
                    stored.delete(save=False)
            raise
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(message='Document uploaded successfully', data={'document_id': document_id})
        )

    @Common().exception_handler
    def delete_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            item = ArtistDocument.get(document_id=params.document_id)
            if not item or item['artist_id'] != profile.artist_id:
                raise ValueError(self.data_no_match)
            ArtistDocument.remove(document_id=params.document_id)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Document deleted successfully')
        )

    @Common(response_handler=DocumentResponseSerializer).exception_handler
    def get_extract(self, params):
        profile = self._get_profile(user_id=params.user_id)
        item = ArtistDocument.get(document_id=params.document_id)
        if not item or item['artist_id'] != profile.artist_id:
            raise ValueError(self.data_no_match)
        utils = ArtistsUtils(entity='document', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper(self._with_file_url([item])))[0]
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    @Common(response_handler=DocumentResponseGetAllSerializer).exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id)
        reversed_mapped = ArtistsUtils.reverse_mapper('document', [params.sort_by, params.filter_key])
        pages = Paginator(
            ArtistDocument.get_all(
                artist_id=profile.artist_id,
                sort_by=reversed_mapped.get(params.sort_by, ''),
                sort_order=params.sort_order,
                filter_key=reversed_mapped.get(params.filter_key, ''),
                filter_value=params.filter_value,
                search_key=params.search_key,
            ),
            per_page=params.limit
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = pages.page(params.page_num)
        utils = ArtistsUtils(entity='document', columns_required=[c for c in params.values.split(',') if c])
        data = json.loads(utils.mapper(self._with_file_url(list(page_data))))
        data = Utils.add_page_parameter(
            final_data=data,
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )

    def download_extract(self, params):
        """Streams a stored KYC file to its owner or to an admin — nobody else. Not wrapped
        in Common().exception_handler because it returns a file, not a JSON envelope; every
        refusal is the same 400 shape the other document endpoints use."""
        def refuse(message):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=Utils.error_response_data(message='Value Error ' + message, error=[message]),
            )

        item = ArtistDocument.objects.filter(document_id=params.document_id).select_related('artist').first()
        if not item:
            return refuse(self.data_no_match)
        user = User.get(user_id=params.user_id)
        is_admin = bool(user) and user['role'] == 'admin'
        if not is_admin and item.artist.user_id != params.user_id:
            return refuse(self.data_no_match)
        stored = item.back_file if params.side == 'back' else item.file
        if not stored:
            return refuse(self.data_no_match)
        try:
            handle = stored.storage.open(stored.name, 'rb')
        except (FileNotFoundError, ValueError):
            return refuse(self.data_no_match)

        extension = os.path.splitext(stored.name)[1].lower()
        safe_type = SAFE_CONTENT_TYPES.get(extension)
        response = FileResponse(handle, content_type=safe_type or 'application/octet-stream')
        # Allow-listed types render inline; anything else (legacy uploads) is forced to download.
        disposition = 'inline' if safe_type else 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="document_{item.document_id}_{params.side}{extension}"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'"
        response['Cache-Control'] = 'private, no-store'
        return response
