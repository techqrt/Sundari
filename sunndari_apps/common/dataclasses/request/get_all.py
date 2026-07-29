from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GetAll:
    values: str
    page_num: int
    limit: int
    sort_by: str
    sort_order: str
    filter_key: str
    filter_value: str
    search_key: str
    from_date: datetime
    to_date: datetime
    present_url: str = None
    user_id: int = None
    artist_id: int = None

    def __post_init__(self):
        self.values_list = (
            [v for v in self.values.split(',') if v]
            if self.values else []
        )
        if not self.sort_by:
            self.sort_by = ''
        if not self.sort_order:
            self.sort_order = 'asc'
        self.ordering = f"{'-' if self.sort_order == 'desc' else ''}{self.sort_by}" if self.sort_by else ''
