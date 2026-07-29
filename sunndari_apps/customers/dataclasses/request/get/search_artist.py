from dataclasses import dataclass


@dataclass
class SearchArtistRequest:
    values: str = ''
    page_num: int = 1
    limit: int = 10
    sort_by: str = 'rating'
    sort_order: str = 'desc'
    search_key: str = ''
    city: str = None
    category_id: int = None
    sub_category_id: int = None
    min_price: float = None
    max_price: float = None
    min_rating: float = None
    present_url: str = None

    def __post_init__(self):
        self.values_list = (
            [v for v in self.values.split(',') if v]
            if self.values else []
        )
        if not self.sort_by:
            self.sort_by = 'rating'
        if not self.sort_order:
            self.sort_order = 'desc'
