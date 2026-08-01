import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common


class CustomersUtils:
    MAPS = {
        'artist_search': {
            'artist_id': 'artistId',
            'user__name': 'name',
            'bio': 'bio',
            'city': 'city',
            'years_experience': 'yearsExperience',
            'avg_rating': 'avgRating',
            'total_reviews': 'totalReviews',
            'starting_price': 'startingPrice',
        },
        'booking': {
            'booking_id': 'bookingId',
            'customer_id': 'customerId',
            'artist_id': 'artistId',
            'sub_category_id': 'subCategoryId',
            'package_id': 'packageId',
            'location_type_id': 'locationTypeId',
            'address_id': 'addressId',
            'booking_date': 'bookingDate',
            'start_time': 'startTime',
            'end_time': 'endTime',
            'status_id': 'statusId',
            'total_amount': 'totalAmount',
            'notes': 'notes',
            'cancelled_by': 'cancelledBy',
            'cancellation_reason': 'cancellationReason',
            'expires_at': 'expiresAt',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'payment': {
            'payment_id': 'paymentId',
            'booking_id': 'bookingId',
            'customer_id': 'customerId',
            'artist_id': 'artistId',
            'payment_type': 'paymentType',
            'amount': 'amount',
            'commission_amount': 'commissionAmount',
            'artist_payout_amount': 'artistPayoutAmount',
            'status_id': 'statusId',
            'gateway': 'gateway',
            'gateway_order_id': 'gatewayOrderId',
            'gateway_payment_id': 'gatewayPaymentId',
            'paid_at': 'paidAt',
            'failure_reason': 'failureReason',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        },
        'review': {
            'review_id': 'reviewId',
            'booking_id': 'bookingId',
            'customer_id': 'customerId',
            'artist_id': 'artistId',
            'rating': 'rating',
            'comment': 'comment',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
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
        reverse_map = {v: k for k, v in CustomersUtils.MAPS.get(entity, {}).items()}
        return {field: reverse_map.get(field, '') for field in fields}
