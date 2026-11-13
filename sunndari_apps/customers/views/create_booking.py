import logging
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sunndari.config import Configurations
from sunndari_apps.common.common import Common
from sunndari_apps.common.utils import Utils
from sunndari_apps.artists.models.artist_profile import ArtistProfile
from sunndari_apps.artists.models.pricing_package import PricingPackage
from sunndari_apps.artists.models.artist_location_preference import ArtistLocationPreference
from sunndari_apps.artists.models.addon import PackageAddOn
from sunndari_apps.artists.models.service_area import ArtistServiceArea
from sunndari_apps.artists.models.salon_address import ArtistSalonAddress
from sunndari_apps.core.models.location_type import LocationType
from sunndari_apps.core.models.booking_status import BookingStatus
from sunndari_apps.users.models.customer_address import CustomerAddress
from sunndari_apps.customers.models.booking import Booking, IST
from sunndari_apps.customers.models.booking_addon import BookingAddOn
from sunndari_apps.customers.slot_rules import slot_end_time, validate_slot, buffers_for
from sunndari_apps.customers.dataclasses.request.create.create_booking import CreateBookingRequest
from sunndari_apps.customers.firebase_utils import BookingFirebaseUtils
from sunndari_apps.notifications.utils import NotificationService
from sunndari_apps.authentication.utils import send_otp_sms, send_otp_email
from sunndari_apps.core.models.service_sub_category import ServiceSubCategory
from sunndari.constants import Constants


logger = logging.getLogger(__name__)


class CreateBookingView:

    @Common().exception_handler
    def create_extract(self, params: CreateBookingRequest):
        with transaction.atomic():
            today_ist = timezone.now().astimezone(IST).date()
            if params.booking_date < today_ist:
                raise ValueError(Constants.past_date_booking)

            booking_start_moment = Booking.to_aware(params.booking_date, params.start_time)
            if booking_start_moment < timezone.now() + timedelta(hours=Configurations.min_booking_advance_hours):
                raise ValueError(Constants.booking_too_soon)

            artist = ArtistProfile.objects.filter(
                artist_id=params.artist_id, approval_status__name='approved',
            ).first()
            if not artist:
                raise ValueError(Constants.artist_not_found)
            if artist.user_id == params.user_id:
                # No role check exists (an account is one role), so the ownership test is the guard:
                # a self-booking would earn cashback and allow a self-review.
                raise ValueError(Constants.self_booking_not_allowed)
            # Bookings ON and the registration payment settled (or exempt): the same test customer search uses.
            # An approved artist who fails it is simply "not accepting"; the payment reason is theirs alone.
            if (not artist.is_accepting_bookings or artist.accepting_locked_by_admin
                    or not ArtistProfile.is_eligible(artist.artist_id)):
                raise ValueError(Constants.artist_not_accepting)

            package = PricingPackage.objects.filter(
                package_id=params.package_id, artist_id=params.artist_id,
            ).first()
            if not package:
                raise ValueError(Constants.data_no_match)
            if not package.is_active:
                raise ValueError(Constants.package_unavailable)
            ServiceSubCategory.assert_live([package.sub_category_id])

            if not ArtistLocationPreference.objects.filter(
                artist_id=params.artist_id, location_type_id=params.location_type_id,
            ).exists():
                raise ValueError(Constants.slot_unavailable)

            location_name = LocationType.objects.filter(
                location_type_id=params.location_type_id,
            ).values_list('name', flat=True).first()
            address_id = params.address_id
            salon_address = None
            if location_name == LocationType.IN_SALON:
                # The customer must pick one of THIS artist's live salons; nothing is chosen for them, and a home
                # address is not part of an In-Salon booking (anything sent in address_id is ignored).
                if not params.salon_address_id:
                    raise ValueError(Constants.salon_address_required)
                salon_address = ArtistSalonAddress.get_active_owned(params.artist_id, params.salon_address_id)
                if not salon_address:
                    raise ValueError(Constants.salon_address_unavailable)
                address_id = None
            else:
                if params.salon_address_id:
                    raise ValueError(Constants.salon_address_not_allowed)
                if not address_id:
                    raise ValueError(Constants.customer_address_required)
                if not CustomerAddress.objects.filter(address_id=address_id, user_id=params.user_id).exists():
                    raise ValueError(Constants.data_no_match)

            # Add-ons: must be the artist's own, active, and linked to this package.
            requested_addon_ids = set(params.addon_ids or [])
            addons = list(PackageAddOn.objects.filter(
                addon_id__in=requested_addon_ids, artist_id=params.artist_id, is_active=True, packages=package,
            ).distinct()) if requested_addon_ids else []
            if len(addons) != len(requested_addon_ids):
                raise ValueError(Constants.addon_not_available)

            # Travel: only Home Visits, and only once the artist has configured service areas
            # (an artist with none keeps the previous behaviour — no restriction, no charge).
            travel_fee = Decimal('0.00')
            if location_name == 'Home Visit' and ArtistServiceArea.has_active(params.artist_id):
                if not params.address_id:
                    raise ValueError(Constants.service_area_address_required)
                address_city = CustomerAddress.objects.filter(
                    address_id=params.address_id, user_id=params.user_id,
                ).values_list('city', flat=True).first()
                area = ArtistServiceArea.find_for_city(params.artist_id, address_city)
                if not area:
                    raise ValueError(Constants.service_area_outside)
                if area.travel_charge_type == 'per_visit':
                    travel_fee = area.charge_amount

            # The total is always computed here — nothing the client sends affects the price.
            total_amount = package.price + sum((addon.price for addon in addons), Decimal('0')) + travel_fee
            commission_rate = artist.commission_rate
            platform_fee = round(total_amount * commission_rate / 100, 2)

            total_duration = package.duration_minutes + sum(addon.duration_minutes for addon in addons)
            end_time = slot_end_time(params.booking_date, params.start_time, total_duration)
            travel_before, return_buffer = buffers_for(location_name, artist)
            validate_slot(
                params.artist_id, params.booking_date, params.start_time, end_time,
                travel_before=travel_before, return_buffer=return_buffer,
            )

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
                total_amount=total_amount,
                address_id=address_id,
                salon_address=salon_address,
                notes=params.notes or None,
                lock_minutes=Configurations.slot_lock_minutes,
                travel_fee=travel_fee,
                commission_rate=commission_rate,
                platform_fee=platform_fee,
                net_amount=total_amount - platform_fee,
                travel_minutes_before=travel_before,
                return_buffer_minutes=return_buffer,
            )
            BookingAddOn.objects.bulk_create([
                BookingAddOn(
                    booking_id=booking_id, addon_id=addon.addon_id, name=addon.name,
                    price=addon.price, duration_minutes=addon.duration_minutes,
                ) for addon in addons
            ])
            booking_otp = Booking.generate_booking_otp(
                booking_id=booking_id, booking_date=params.booking_date, end_time=end_time,
            )
        # The artist is told about this booking (and sent its OTP) only once it is paid; see
        # customers/booking_alerts.py. Until then it is invisible to them.
        BookingFirebaseUtils.sync_booking(booking_id=booking_id)
        return Response(
            status=status.HTTP_201_CREATED,
            data=Utils.success_response_data(
                message=Constants.slot_locked,
                data={'booking_id': booking_id, 'total_amount': str(total_amount), 'travel_fee': str(travel_fee)},
            )
        )
