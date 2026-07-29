import dataclasses


@dataclasses.dataclass
class ServiceSubCategoryGetRequest:
    sub_category_id: int = None
    values: str = ''
    user_id: int = None
    present_url: str = None
