import json
import pandas
import numpy as np
from sunndari_apps.common.common import Common


class ChatUtils:
    MAPS = {
        'conversation': {
            'conversation_id': 'conversationId',
            'booking_id': 'bookingId',
            'is_open': 'isOpen',
            'created_at': 'createdAt',
        },
        'message': {
            'message_id': 'messageId',
            'conversation_id': 'conversationId',
            'sender_id': 'senderId',
            'content': 'content',
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
        reverse_map = {v: k for k, v in ChatUtils.MAPS.get(entity, {}).items()}
        return {field: reverse_map.get(field, '') for field in fields}
