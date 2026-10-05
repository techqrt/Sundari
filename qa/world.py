import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from sunndari_apps.artists.models import (
    ArtistProfile, PricingPackage, ArtistLocationPreference, ArtistAvailabilitySchedule, ArtistServiceOffering,
)
from sunndari_apps.core.models import (
    ApprovalStatus, BookingStatus, PaymentStatus, ServiceCategory, ServiceSubCategory, LocationType,
)
from sunndari_apps.users.models.customer_address import CustomerAddress
from sunndari_apps.payments.models import Payment
from qa.harness import make_actor, data, future_date, fmt_date


def png(name='img.png', size=(8, 8), fmt='PNG', ctype='image/png'):
    buf = io.BytesIO()
    Image.new('RGB', size, (10, 120, 200)).save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=ctype)


def png_bytes(fmt='PNG'):
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 120, 200)).save(buf, format=fmt)
    return buf.getvalue()


def seed_statuses():
    for n in ('pending', 'approved', 'rejected', 'suspended'):
        ApprovalStatus.objects.get_or_create(name=n, defaults={'description': n})
    for n in ('pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show'):
        BookingStatus.objects.get_or_create(name=n, defaults={'description': n})
    for n in ('pending', 'paid', 'failed', 'refunded', 'partially_refunded'):
        PaymentStatus.objects.get_or_create(name=n, defaults={'description': n})


def make_bookable_artist(phone, name, price=1500, duration=60, approved=True):
    seed_statuses()
    actor = make_actor('artist', phone, name)
    profile = ArtistProfile.create_for_user(actor.id)
    profile = ArtistProfile.objects.get(user_id=actor.id)
    if approved:
        profile.approval_status = ApprovalStatus.objects.get(name='approved')
    profile.display_name = name
    profile.city = 'Lucknow'
    profile.save()
    cat, _ = ServiceCategory.objects.get_or_create(name='QA Makeup')
    sub, _ = ServiceSubCategory.objects.get_or_create(category=cat, name='QA Bridal')
    ArtistServiceOffering.add(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id)
    pkg = PricingPackage.objects.create(artist=profile, sub_category=sub, name=f'{name} package', price=Decimal(price), duration_minutes=duration)
    for lt in ('Home Visit', 'Studio'):
        loc, _ = LocationType.objects.get_or_create(name=lt)
        ArtistLocationPreference.add(artist_id=profile.artist_id, location_type_id=loc.location_type_id)
    for dow in range(7):
        ArtistAvailabilitySchedule.objects.create(artist=profile, day_of_week=dow, start_time='06:00:00', end_time='22:00:00')
    actor.profile, actor.package, actor.sub = profile, pkg, sub
    return actor


def make_customer(phone, name, city='Lucknow'):
    seed_statuses()
    actor = make_actor('customer', phone, name)
    addr = CustomerAddress.objects.get(address_id=CustomerAddress().create(user_id=actor.id, address_line_1='1 QA Road', city=city, pin_code='226001'))
    actor.address = addr
    return actor


def make_admin(phone='+919400009999'):
    return make_actor('admin', phone, 'QA Admin')


def location(name):
    return LocationType.objects.get(name=name)


def create_booking(customer, artist, start='10:00:00', day=3, location_name='Home Visit', addon_ids=None, address=True):
    payload = {
        'artist_id': artist.profile.artist_id, 'package_id': artist.package.package_id,
        'location_type_id': location(location_name).location_type_id,
        'booking_date': fmt_date(future_date(day)), 'start_time': start,
    }
    if address:
        payload['address_id'] = customer.address.address_id
    if addon_ids:
        payload['addon_ids'] = addon_ids
    return customer.client.post('/customers/bookings/create/', payload, format='json')


def pay(booking_id):
    """Simulates a settled payment (the real gateway is unavailable) — direct row, status 'paid'."""
    from sunndari_apps.customers.models import Booking
    booking = Booking.objects.get(booking_id=booking_id)
    Payment().create(
        booking_id=booking_id, customer_id=booking.customer_id, artist_id=booking.artist_id,
        amount=booking.total_amount, commission_amount=Decimal('0'), artist_payout_amount=booking.total_amount,
        status_id=PaymentStatus.objects.get(name='paid').status_id,
    )


def confirmed_booking(customer, artist, **kw):
    resp = create_booking(customer, artist, **kw)
    booking_id = data(resp)['booking_id']
    pay(booking_id)
    artist.client.put('/artists/bookings/update_status/', {'booking_id': booking_id, 'status': 'confirmed'}, format='json')
    return booking_id
