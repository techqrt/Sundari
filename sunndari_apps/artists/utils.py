import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common


class ArtistsUtils:
    MAPS = {
        'profile': {
            'artist_id': 'artistId',
            'user_id': 'userId',
            'bio': 'bio',
            'years_experience': 'yearsExperience',
            'city': 'city',
            'service_radius_km': 'serviceRadiusKm',
            'avg_rating': 'avgRating',
            'total_reviews': 'totalReviews',
            'commission_rate': 'commissionRate',
            'approval_status_id': 'approvalStatusId',
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
    }

    def __init__(self, entity: str, columns_required: list = None) -> None:
        self.columns_required = columns_required or []
        self.entity = entity
        self.mapped_columns_name = self.MAPS.get(entity, {})

    @staticmethod
    def flatten_to_nested_dict(df):
        result = []
        df = df.map(
            lambda x: x.isoformat() if isinstance(x, (pandas.Timestamp,)) or hasattr(x, 'isoformat')
            else (None if (isinstance(x, float) and pandas.isna(x)) else x)
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
    def reverse_mapper(entity: str, fields: list) -> dict:
        reverse_map = {v: k for k, v in ArtistsUtils.MAPS.get(entity, {}).items()}
        return {field: reverse_map.get(field, '') for field in fields}
