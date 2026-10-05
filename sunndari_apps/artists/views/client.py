import json
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q
from rest_framework import status
from rest_framework.response import Response

from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.common.dataclasses.request.get_all import GetAll
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.client_note import ArtistClientNote
from sunndari_apps.customers.models.booking import Booking
from sunndari.constants import Constants

# A client is someone with at least one real booking: paid/confirmed, started or done.
# Unpaid pending requests and cancelled ones don't make someone "my client".
CLIENT_STATUSES = ['confirmed', 'in_progress', 'completed']


class ArtistClientView:

    def _get_profile(self, user_id: int) -> ArtistProfile:
        profile = ArtistProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise ValueError(Constants.artist_not_found)
        return profile

    @Common().exception_handler
    def get_all_extract(self, params: GetAll):
        profile = self._get_profile(user_id=params.user_id)
        qs = Booking.objects.filter(artist_id=profile.artist_id, status__name__in=CLIENT_STATUSES)
        if params.search_key:
            qs = qs.filter(customer__name__icontains=params.search_key)
        clients = qs.values('customer_id', 'customer__name').annotate(
            bookings_count=Count('booking_id'),
            completed_bookings=Count('booking_id', filter=Q(status__name='completed')),
            last_booking_date=Max('booking_date'),
        )
        sort_map = {'name': 'customer__name', 'lastBookingDate': 'last_booking_date', 'bookingsCount': 'bookings_count'}
        sort_field = sort_map.get(params.sort_by, 'last_booking_date')
        direction = '' if (params.sort_by and params.sort_order == 'asc') else '-'
        clients = clients.order_by(direction + sort_field, 'customer_id')

        pages = Paginator(list(clients), per_page=params.limit)
        if pages.num_pages < params.page_num:
            raise ValueError('Page limit exceeded!')
        rows = list(pages.page(params.page_num))
        notes = {
            n['customer_id']: n for n in ArtistClientNote.objects.filter(
                artist_id=profile.artist_id, customer_id__in=[r['customer_id'] for r in rows],
            ).values('customer_id', 'note', 'updated_at')
        }
        data = [{
            'customerId': r['customer_id'],
            'name': r['customer__name'],
            'bookingsCount': r['bookings_count'],
            'completedBookings': r['completed_bookings'],
            'lastBookingDate': r['last_booking_date'],
            'note': notes.get(r['customer_id'], {}).get('note'),
            'noteUpdatedAt': notes.get(r['customer_id'], {}).get('updated_at'),
        } for r in rows]
        data = Utils.add_page_parameter(
            final_data=json.loads(json.dumps(data, default=str)),
            page_num=params.page_num,
            total_page=pages.num_pages,
            present_url=params.present_url,
            next_page_required=pages.num_pages != params.page_num,
        )
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message=Constants.data_get, data=data)
        )

    @Common().exception_handler
    def set_note_extract(self, params):
        with transaction.atomic():
            profile = self._get_profile(user_id=params.user_id)
            is_client = Booking.objects.filter(
                artist_id=profile.artist_id, customer_id=params.customer_id, status__name__in=CLIENT_STATUSES,
            ).exists()
            if not is_client:
                raise ValueError(Constants.data_no_match)
            if params.note.strip():
                ArtistClientNote.objects.update_or_create(
                    artist_id=profile.artist_id, customer_id=params.customer_id,
                    defaults={'note': params.note.strip()},
                )
            else:
                ArtistClientNote.objects.filter(artist_id=profile.artist_id, customer_id=params.customer_id).delete()
        return Response(
            status=status.HTTP_200_OK,
            data=Utils.success_response_data(message='Client note saved successfully')
        )
