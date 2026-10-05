from collections import Counter
from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.customers.models.booking import Booking
from sunndari.constants import Constants


class ArtistInsightsView:
    """Read-only business numbers for the logged-in artist, derived from bookings — nothing
    here is stored. Money figures (earnings) are deliberately not part of this yet."""

    @Common().exception_handler
    def summary_extract(self, params: GetAll):
        profile = ArtistProfile.objects.filter(user_id=params.user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        bookings = Booking.objects.filter(artist_id=profile.artist_id)
        from_date = params.from_date.date() if params.from_date else None
        to_date = params.to_date.date() if params.to_date else None
        if from_date and to_date and from_date > to_date:
            raise ValueError('from_date must not be after to_date')
        if from_date:
            bookings = bookings.filter(booking_date__gte=from_date)
        if to_date:
            bookings = bookings.filter(booking_date__lte=to_date)

        by_status = Counter(dict(bookings.values_list('status__name').annotate(n=Count('booking_id'))))
        completed = bookings.filter(status__name='completed')
        # Repeat client = a customer this artist completed 2+ bookings for in the period.
        repeat_clients = sum(
            1 for count in completed.values('customer_id').annotate(n=Count('booking_id')).values_list('n', flat=True)
            if count >= 2
        )
        top_services = [
            {'subCategoryId': row['sub_category_id'], 'name': row['sub_category__name'], 'bookings': row['n']}
            for row in bookings.filter(status__name__in=['confirmed', 'in_progress', 'completed'])
            .values('sub_category_id', 'sub_category__name').annotate(n=Count('booking_id'))
            .order_by('-n', 'sub_category__name')[:5]
        ]
        data = {
            'fromDate': from_date, 'toDate': to_date,
            'totalBookings': sum(by_status.values()),
            'bookingsByStatus': dict(by_status),
            'completedBookings': by_status.get('completed', 0),
            'cancelledBookings': by_status.get('cancelled', 0),
            'repeatClients': repeat_clients,
            'topServices': top_services,
            # Lifetime total (views are not tracked per day).
            'profileViews': profile.profile_view_count,
        }
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )
