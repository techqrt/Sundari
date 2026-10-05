import json
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.utils import Utils
from sunndari_apps.customers.models.reschedule import BookingReschedule
from sunndari_apps.customers.utils import CustomersUtils
from sunndari.constants import Constants


def list_reschedules(params, customer_id: int = None, artist_id: int = None) -> Response:
    """Paginated reschedule history for one side of the marketplace. Use
    filter_key=bookingId&filter_value=<id> to narrow it to a single booking."""
    BookingReschedule.expire_stale()
    reversed_mapped = CustomersUtils.reverse_mapper('reschedule', [params.sort_by, params.filter_key])
    pages = Paginator(
        BookingReschedule.get_all(
            customer_id=customer_id,
            artist_id=artist_id,
            sort_by=reversed_mapped.get(params.sort_by, ''),
            sort_order=params.sort_order,
            filter_key=reversed_mapped.get(params.filter_key, ''),
            filter_value=params.filter_value,
            search_key=params.search_key,
        ),
        per_page=params.limit,
    )
    if pages.num_pages < params.page_num:
        raise ValueError('Page limit exceeded!')
    utils = CustomersUtils(entity='reschedule', columns_required=[c for c in params.values.split(',') if c])
    data = json.loads(utils.mapper(list(pages.page(params.page_num))))
    data = Utils.add_page_parameter(
        final_data=data,
        page_num=params.page_num,
        total_page=pages.num_pages,
        present_url=params.present_url,
        next_page_required=pages.num_pages != params.page_num,
    )
    return Response(status=status.HTTP_200_OK, data=Utils.success_response_data(message=Constants.data_get, data=data))
