from datetime import datetime, timedelta
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.availability_schedule import ArtistAvailabilitySchedule
from sunndari_apps.artists.models.availability_block import ArtistAvailabilityBlock
from sunndari_apps.artists.models.artist_location_preference import ArtistLocationPreference
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.users.models.customer_address import CustomerAddress
from sunndari_apps.customers.models.booking import Booking
from sunndari_apps.customers.dataclasses.request.create.create_booking import CreateBookingRequest
from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
from sunndari_apps.notifications.utils import NotificationService
from sunndari.constants import Constants


class CreateBookingView:

    @Common().exception_handler
    def create_extract(self, params: CreateBookingRequest):
        with transaction.atomic():
            artist = ArtistProfile.objects.filter(
                artist_id=params.artist_id, approval_status__name='approved',
            ).first()
            if not artist:
                raise ValueError(Constants.artist_not_found)

            package = PricingPackage.objects.filter(
                package_id=params.package_id, artist_id=params.artist_id, is_active=True,
            ).first()
            if not package:
                raise ValueError(Constants.data_no_match)

            if not ArtistLocationPreference.objects.filter(
                artist_id=params.artist_id, location_type_id=params.location_type_id,
            ).exists():
                raise ValueError(Constants.slot_unavailable)

            if params.address_id and not CustomerAddress.objects.filter(
                address_id=params.address_id, user_id=params.user_id,
            ).exists():
                raise ValueError(Constants.data_no_match)

            start_dt = datetime.combine(params.booking_date, params.start_time)
            end_dt = start_dt + timedelta(minutes=package.duration_minutes)
            end_time = end_dt.time()
            if end_dt.date() != params.booking_date:
                raise ValueError(Constants.slot_unavailable)

            if ArtistAvailabilityBlock.objects.filter(
                artist_id=params.artist_id, block_date=params.booking_date,
            ).exists():
                raise ValueError(Constants.slot_unavailable)

            day_of_week = params.booking_date.weekday()
            schedule = ArtistAvailabilitySchedule.objects.filter(
                artist_id=params.artist_id, day_of_week=day_of_week, is_active=True,
            ).first()
            if not schedule or schedule.start_time > params.start_time or end_time > schedule.end_time:
                raise ValueError(Constants.slot_unavailable)

            locked_bookings = list(Booking.objects.select_for_update().filter(
                artist_id=params.artist_id,
                booking_date=params.booking_date,
                status__name__in=Booking.ACTIVE_STATUSES,
            ))
            for existing in locked_bookings:
                if existing.start_time < end_time and existing.end_time > params.start_time:
                    raise ValueError(Constants.double_booking)

            pending_status = BookingStatus.objects.filter(name='pending').first()
            booking_id = Booking().create(
                customer_id=params.user_id,
                artist_id=params.artist_id,
                sub_category_id=package.sub_category_id,
                package_id=package.package_id,
                location_type_id=params.location_type_id,
                booking_date=params.booking_date,
                start_time=params.start_time,
                end_time=end_time,
                status_id=pending_status.status_id,
                total_amount=package.price,
                address_id=params.address_id,
                notes=params.notes or None,
                lock_minutes=Configurations.slot_lock_minutes,
            )
        NotificationService.notify(
            user_id=artist.user_id,
            title='New booking request',
            message=f'You have a new booking request for {params.booking_date}.',
            type='new_booking_alert',
            booking_id=booking_id,
        )
        BookingFirebaseUtils.sync_booking(booking_id=booking_id)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message=Constants.slot_locked,
                data={'booking_id': booking_id},
            )
        )
