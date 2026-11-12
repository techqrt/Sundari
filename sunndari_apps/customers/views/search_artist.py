import json
from django.core.paginator import Paginator
from django.db.models import Min, Q
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
from sunndari_apps.customers.serializers.response.get_all.search_artist import ArtistSearchResponseGetAllSerializer
from sunndari_apps.customers.dataclasses.request.get.search_artist import SearchArtistRequest
from sunndari_apps.customers.utils import CustomersUtils
from sunndari.constants import Constants


class SearchArtistView:
    def __init__(self):
        self.data_get = Constants.data_get

    SORT_MAP = {
        'rating': 'avg_rating',
        'price': 'starting_price',
        'experience': 'years_experience',
        'name': 'user__name',
    }

    @Common(response_handler=ArtistSearchResponseGetAllSerializer).exception_handler
    def search_extract(self, params: SearchArtistRequest):
        # Only packages that can actually be booked count: the package is active AND its service (and that
        # service's category) is live. An artist whose every package is under a switched-off service
        # therefore disappears from search, exactly as one with no active package already did.
        bookable = Q(pricing_packages__is_active=True, **ServiceSubCategory.live_filter('pricing_packages__sub_category__'))
        qs = ArtistProfile.objects.filter(ArtistProfile.public_filter()).annotate(
            starting_price=Min('pricing_packages__price', filter=bookable),
        ).filter(starting_price__isnull=False)

        if params.city:
            qs = qs.filter(city__icontains=params.city)
        if params.min_rating is not None:
            qs = qs.filter(avg_rating__gte=params.min_rating)
        if params.min_price is not None:
            qs = qs.filter(starting_price__gte=params.min_price)
        if params.max_price is not None:
            qs = qs.filter(starting_price__lte=params.max_price)
        if params.sub_category_id:
            qs = qs.filter(bookable, pricing_packages__sub_category_id=params.sub_category_id)
        elif params.category_id:
            qs = qs.filter(bookable, pricing_packages__sub_category__category_id=params.category_id)
        if params.search_key:
            qs = qs.filter(Q(user__name__icontains=params.search_key) | Q(bio__icontains=params.search_key))

        sort_field = self.SORT_MAP.get(params.sort_by, 'avg_rating')
        qs = qs.distinct().order_by(('-' if params.sort_order == 'desc' else '') + sort_field)

        pages = Paginator(
            qs.values(
                'artist_id', 'user__name', 'bio', 'city', 'years_experience',
                'avg_rating', 'total_reviews', 'starting_price',
            ),
            per_page=params.limit,
        )
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        page_data = list(pages.page(params.page_num))
        utils = CustomersUtils(entity='artist_search')
        data = json.loads(utils.mapper(page_data))
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
