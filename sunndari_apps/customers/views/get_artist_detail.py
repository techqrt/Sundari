import json
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.package_inclusion import PackageInclusion
from sunndari_apps.artists.models.portfolio import Portfolio
from sunndari_apps.artists.models.artist_service_offering import ArtistServiceOffering
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari_apps.customers.serializers.response.get.get_artist_detail import ArtistDetailResponseSerializer
from sunndari_apps.customers.dataclasses.request.get.get_artist_detail import ArtistDetailRequest
from sunndari.constants import Constants


class ArtistDetailView:
    def __init__(self):
        self.data_get = Constants.data_get

    @Common(response_handler=ArtistDetailResponseSerializer).exception_handler
    def get_extract(self, params: ArtistDetailRequest):
        profile_dict = ArtistProfile.objects.filter(
            artist_id=params.artist_id,
            approval_status__name='approved',
        ).values(
            'artist_id', 'user_id', 'bio', 'years_experience', 'city',
            'service_radius_km', 'avg_rating', 'total_reviews',
            'commission_rate', 'approval_status_id', 'created_at', 'updated_at',
        ).first()
        if not profile_dict:
            raise ValueError(Constants.artist_not_found)

        profile_data = json.loads(ArtistsUtils(entity='profile').mapper([profile_dict]))[0]

        packages_raw = list(PricingPackage.objects.filter(
            artist_id=params.artist_id, is_active=True,
        ).values(
            'package_id', 'artist_id', 'sub_category_id', 'name',
            'price', 'duration_minutes', 'description', 'is_active', 'created_at', 'updated_at',
        ))
        packages_data = json.loads(ArtistsUtils(entity='package').mapper(packages_raw))
        for i, pkg in enumerate(packages_raw):
            inclusions_raw = PackageInclusion.get_for_package(package_id=pkg['package_id'])
            packages_data[i]['inclusions'] = json.loads(ArtistsUtils(entity='inclusion').mapper(inclusions_raw))

        portfolio_raw = list(Portfolio.objects.filter(
            artist_id=params.artist_id, is_active=True,
        ).values(
            'portfolio_id', 'artist_id', 'file', 'media_type', 'sub_category_id',
            'caption', 'approval_status_id', 'is_active', 'created_at', 'updated_at',
        ))
        portfolio_data = json.loads(ArtistsUtils(entity='portfolio').mapper(portfolio_raw))

        services_raw = list(ArtistServiceOffering.objects.filter(
            artist_id=params.artist_id, is_active=True,
        ).values(
            'offering_id', 'artist_id', 'sub_category_id',
            'custom_price', 'custom_duration_minutes', 'is_active', 'created_at',
        ))
        services_data = json.loads(ArtistsUtils(entity='service_offering').mapper(services_raw))

        data = {
            'profile': profile_data,
            'packages': packages_data,
            'portfolio': portfolio_data,
            'services': services_data,
        }
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=self.data_get, data=data)
        )
