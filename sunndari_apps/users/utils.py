import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common


class UsersUtils:
    def __init__(self, entity: str, columns_required: list = []) -> None:
        self.columns_required = columns_required
        self.entity = entity

        address_map = {
            'address_id': 'addressId',
            'user_id': 'userId',
            'address_line_1': 'addressLine1',
            'address_line_2': 'addressLine2',
            'city': 'city',
            'pin_code': 'pinCode',
            'is_default': 'isDefault',
            'created_at': 'createdAt',
            'updated_at': 'updatedAt',
        }

        profile_map = {
            'user_id': 'userId',
            'phone_number': 'phoneNumber',
            'name': 'name',
            'email': 'email',
            'role': 'role',
            'is_active': 'isActive',
            'created_date_time': 'createdAt',
        }

        self.mapped_columns_name = (
            address_map if entity == 'address' else profile_map
        )

    @staticmethod
    def flatten_to_nested_dict(df):
        result = []
        df = df.map(
            lambda x: x.isoformat() if isinstance(x, pandas.Timestamp)
            else (None if pandas.isna(x) else x)
        )
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        for _, row in df.iterrows():
            row_dict = {}
            for col, val in row.items():
                if '.' in col:
                    parts = col.split('.')
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
                columns_required=self.columns_required
            )
            dataframe = dataframe[self.columns_required]
        flatten_data, _ = self.flatten_to_nested_dict(dataframe)
        return json.dumps(flatten_data, default=str)

    @staticmethod
    def reverse_mapper(fields: list) -> dict:
        combined_map = {}
        combined_map.update(UsersUtils('address').mapped_columns_name)
        combined_map.update(UsersUtils('profile').mapped_columns_name)
        reverse_map = {v: k for k, v in combined_map.items()}
        return {field: reverse_map.get(field, '') for field in fields}
