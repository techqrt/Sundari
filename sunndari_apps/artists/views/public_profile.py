import json
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.uploads import absolute_file_url
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.portfolio import Portfolio
from sunndari_apps.artists.models.artist_speciality import ArtistSpeciality
from sunndari_apps.artists.models.service_area import ArtistServiceArea
from sunndari_apps.artists.utils import ArtistsUtils
from sunndari.constants import Constants


class PublicArtistView:
    """The shareable, no-login artist page. Deliberately a *separate, minimal* projection of
    the artist — no user id, commission, review state, contact details, date of birth or
    anything internal — and only for approved artists."""

    @Common().exception_handler
    def get_extract(self, slug: str, present_url: str):
        artist = ArtistProfile.objects.select_related('user').filter(
            public_slug=slug, approval_status__name='approved',
        ).first()
        if not artist:
            raise ValueError(Constants.artist_not_found)
        ArtistProfile.record_view(artist_id=artist.artist_id)

        photo_field = ArtistProfile._meta.get_field('profile_photo')
        packages_raw = list(PricingPackage.objects.filter(artist_id=artist.artist_id, is_active=True).order_by('package_id').values(
            'package_id', 'artist_id', 'sub_category_id', 'name', 'price', 'duration_minutes', 'description',
            'makeup_type', 'brands', 'product_details', 'photo', 'is_active', 'created_at', 'updated_at',
        ))
        portfolio = [
            {'fileUrl': absolute_file_url(Portfolio._meta.get_field('file'), item['file'], present_url),
             'mediaType': item['media_type'], 'caption': item['caption']}
            for item in Portfolio.objects.filter(artist_id=artist.artist_id, is_active=True, is_work_sample=False)
            .order_by('sort_order', 'portfolio_id').values('file', 'media_type', 'caption')
        ]
        data = {
            'displayName': artist.display_name or artist.user.name,
            'profileType': artist.profile_type,
            'bio': artist.bio,
            'city': artist.city,
            'yearsExperience': artist.years_experience,
            'instagramUrl': artist.instagram_url,
            'avgRating': str(artist.avg_rating),
            'totalReviews': artist.total_reviews,
            'isAcceptingBookings': artist.is_accepting_bookings,
            'profilePhotoUrl': absolute_file_url(photo_field, artist.profile_photo.name, present_url),
            'coverPhotoUrl': absolute_file_url(ArtistProfile._meta.get_field('cover_photo'), artist.cover_photo.name, present_url),
            'specialities': [row['sub_category__name'] for row in ArtistSpeciality.get_all(artist_id=artist.artist_id)],
            'serviceAreas': [row['city'] for row in ArtistServiceArea.get_all(artist_id=artist.artist_id, only_active=True)],
            'packages': ArtistsUtils.map_packages(packages_raw, present_url),
            'portfolio': portfolio,
        }
        for package in data['packages']:
            for private in ('artistId', 'isActive', 'createdAt', 'updatedAt'):
                package.pop(private, None)
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )
