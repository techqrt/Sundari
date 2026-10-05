import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common


class ArtistsUtils:
    MAPS = {
        'profile': {
            'artist_id': 'artistId',
            'user_id': 'userId',
            'display_name': 'displayName',
            'date_of_birth': 'dateOfBirth',
            'instagram_url': 'instagramUrl',
            'profile_type': 'profileType',
            'is_accepting_bookings': 'isAcceptingBookings',
            'public_slug': 'publicSlug',
            'profile_view_count': 'profileViewCount',
            'agreement_version': 'agreementVersion',
            'travel_time_before_minutes': 'travelTimeBeforeMinutes',
            'return_buffer_minutes': 'returnBufferMinutes',
            'profile_photo': 'profilePhotoUrl',
            'cover_photo': 'coverPhotoUrl',
            'bio': 'bio',
            'years_experience': 'yearsExperience',
            'city': 'city',
            'service_radius_km': 'serviceRadiusKm',
            'avg_rating': 'avgRating',
            'total_reviews': 'totalReviews',
            'commission_rate': 'commissionRate',
            'approval_status_id': 'approvalStatusId',
            'base_address_id': 'baseAddressId',
            'terms_accepted_at': 'termsAcceptedAt',
            'submitted_for_review_at': 'submittedForReviewAt',
            'rejection_reason': 'rejectionReason',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'service_offering': {
            'offering_id': 'offeringId',
            'artist_id': 'artistId',
            'sub_category_id': 'subCategoryId',
            'custom_price': 'customPrice',
            'custom_duration_minutes': 'customDurationMinutes',
            'is_active': 'isActive',
            'created_at': 'createdAt',
        },
        'location_preference': {
            'preference_id': 'preferenceId',
            'artist_id': 'artistId',
            'location_type_id': 'locationTypeId',
        },
        'portfolio': {
            'portfolio_id': 'portfolioId',
            'artist_id': 'artistId',
            'file': 'fileUrl',
            'media_type': 'mediaType',
            'sub_category_id': 'subCategoryId',
            'caption': 'caption',
            'approval_status_id': 'approvalStatusId',
            'is_active': 'isActive',
            'is_work_sample': 'isWorkSample',
            'sort_order': 'sortOrder',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'package': {
            'package_id': 'packageId',
            'artist_id': 'artistId',
            'sub_category_id': 'subCategoryId',
            'name': 'name',
            'price': 'price',
            'duration_minutes': 'durationMinutes',
            'description': 'description',
            'makeup_type': 'makeupType',
            'product_details': 'productDetails',
            'photo': 'photoUrl',
            'is_active': 'isActive',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'addon': {
            'addon_id': 'addOnId',
            'artist_id': 'artistId',
            'name': 'name',
            'description': 'description',
            'price': 'price',
            'duration_minutes': 'durationMinutes',
            'is_active': 'isActive',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'service_area': {
            'area_id': 'areaId',
            'artist_id': 'artistId',
            'city': 'city',
            'travel_charge_type': 'travelChargeType',
            'charge_amount': 'chargeAmount',
            'is_active': 'isActive',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'inclusion': {
            'inclusion_id': 'inclusionId',
            'package_id': 'packageId',
            'inclusion_text': 'inclusionText',
            'order': 'order',
        },
        'schedule': {
            'schedule_id': 'scheduleId',
            'artist_id': 'artistId',
            'day_of_week': 'dayOfWeek',
            'start_time': 'startTime',
            'end_time': 'endTime',
            'location_type_id': 'locationTypeId',
            'is_active': 'isActive',
        },
        'block': {
            'block_id': 'blockId',
            'artist_id': 'artistId',
            'block_date': 'blockDate',
            'note': 'note',
            'created_at': 'createdAt',
        },
        'document': {
            'document_id': 'documentId',
            'artist_id': 'artistId',
            'document_type': 'documentType',
            'id_type': 'idType',
            'document_number': 'documentNumber',
            'file': 'fileUrl',
            'back_file': 'backFileUrl',
            'verification_status_id': 'verificationStatusId',
            'rejection_reason': 'rejectionReason',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'payout_account': {
            'payout_account_id': 'payoutAccountId',
            'artist_id': 'artistId',
            'account_holder_name': 'accountHolderName',
            'bank_account_number_masked': 'bankAccountNumberMasked',
            'ifsc_code': 'ifscCode',
            'upi_id': 'upiId',
            'verification_status_id': 'verificationStatusId',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'review_feedback': {
            'feedback_id': 'feedbackId',
            'decision': 'decision',
            'message': 'message',
            'created_at': 'createdAt',
        },
        'review_queue': {
            'artist_id': 'artistId',
            'user_id': 'userId',
            'bio': 'bio',
            'years_experience': 'yearsExperience',
            'city': 'city',
            'service_radius_km': 'serviceRadiusKm',
            'approval_status_id': 'approvalStatusId',
            'submitted_for_review_at': 'submittedForReviewAt',
            'created_at': 'createdAt',
        },
    }

    def __init__(self, entity: str, columns_required: list = None) -> None:
        self.columns_required = columns_required or []
        self.entity = entity
        self.mapped_columns_name = self.MAPS.get(entity, {})

    @staticmethod
    def flatten_to_nested_dict(df):
        result = []
        df = df.map(
            # pandas.isna() first — a nullable datetime column that also holds a real
            # timestamp gets upcast to datetime64, turning None into NaT, which still
            # has an isoformat() method (returns the literal string "NaT") unless caught here.
            lambda x: None if pandas.isna(x) else (
                x.isoformat() if isinstance(x, (pandas.Timestamp,)) or hasattr(x, 'isoformat') else x
            )
        )
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        for _, row in df.iterrows():
            row_dict = {}
            for col, val in row.items():
                # pandas upcasts an int column to float64 the moment any row in the same
                # frame has a null in it (needs float to hold NaN) — undo that per value,
                # since a plain dict (unlike a DataFrame column) has no dtype to preserve.
                if isinstance(val, float) and not pandas.isna(val) and val.is_integer():
                    val = int(val)
                if '.' in str(col):
                    parts = str(col).split('.')
                    current = row_dict
                    for part in parts[:-1]:
                        current = current.setdefault(part, {})
                    current[parts[-1]] = val
                else:
                    row_dict[col] = val
            result.append(row_dict)
        return result, df

    def mapper(self, data: list) -> str:
        if not data:
            return '[]'
        dataframe = pandas.DataFrame.from_records(data)
        dataframe.rename(columns=self.mapped_columns_name, inplace=True)
        if self.columns_required:
            Common.mapper_value_error(
                mapped_column_names=self.mapped_columns_name,
                columns_required=self.columns_required,
            )
            dataframe = dataframe[self.columns_required]
        flatten_data, _ = self.flatten_to_nested_dict(dataframe)
        return json.dumps(flatten_data, default=str)

    @staticmethod
    def map_addons(raw_rows: list) -> list:
        """Add-on dicts -> API objects; `package_ids` (a list) is kept out of the pandas
        mapper, which cannot hold list cells, and re-attached as packageIds."""
        if not raw_rows:
            return []
        flat_rows = [{key: value for key, value in raw.items() if key != 'package_ids'} for raw in raw_rows]
        mapped = json.loads(ArtistsUtils(entity='addon').mapper(flat_rows))
        for raw, data in zip(raw_rows, mapped):
            data['packageIds'] = raw.get('package_ids', [])
        return mapped

    @staticmethod
    def map_packages(raw_rows: list, present_url: str = None) -> list:
        """Package dicts -> API objects: photo as an absolute URL, brands as a real list
        (kept out of the pandas mapper, which cannot hold list cells) and the derived
        category of the package's sub-category."""
        from sunndari_apps.common.uploads import absolute_file_url
        from sunndari_apps.artists.models.pricing_package import PricingPackage
        from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
        if not raw_rows:
            return []
        photo_field = PricingPackage._meta.get_field('photo')
        flat_rows = []
        for raw in raw_rows:
            row = {key: value for key, value in raw.items() if key != 'brands'}
            row['photo'] = absolute_file_url(photo_field, raw.get('photo'), present_url)
            flat_rows.append(row)
        mapped = json.loads(ArtistsUtils(entity='package').mapper(flat_rows))
        sub_categories = {
            sub.sub_category_id: sub for sub in ServiceSubCategory.objects.filter(
                sub_category_id__in={raw['sub_category_id'] for raw in raw_rows},
            ).select_related('category')
        }
        for raw, data in zip(raw_rows, mapped):
            data['brands'] = raw.get('brands') or []
            sub_category = sub_categories.get(raw['sub_category_id'])
            data['category'] = (
                {'categoryId': sub_category.category_id, 'name': sub_category.category.name} if sub_category else None
            )
        return mapped

    @staticmethod
    def reverse_mapper(entity: str, fields: list) -> dict:
        reverse_map = {v: k for k, v in ArtistsUtils.MAPS.get(entity, {}).items()}
        return {field: reverse_map.get(field, '') for field in fields}
