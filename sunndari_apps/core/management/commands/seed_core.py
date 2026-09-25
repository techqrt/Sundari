from django.core.management.base import BaseCommand
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus,
)

CATEGORIES = [
    {
        'name': 'Makeup',
        'description': 'Professional makeup services for bridal, festive, and everyday occasions',
        'services': [
            ('Bridal Makeup', 'Full bridal makeup with setting spray, includes skin prep and final look'),
            ('Pre-Bridal Makeup', 'Trial or event-adjacent makeup session ahead of the wedding day'),
            ('Engagement Makeup', 'Elegant makeup look for engagement ceremonies'),
            ('Reception Makeup', 'Glamorous makeup for wedding reception events'),
            ('Party Makeup', 'Glamorous party-ready makeup using MAC / KRYOLAN products'),
            ('HD Makeup', 'High-definition makeup that looks flawless on camera'),
            ('Airbrush Makeup', 'Airbrush foundation makeup for a seamless, long-lasting finish'),
            ('Natural / Dewy Makeup', 'Light, skin-like makeup for everyday or daytime events'),
            ('Dulha Grooming', 'Groom grooming package: facial, cleanup, and styling'),
        ],
    },
    {
        'name': 'Additional Services',
        'description': 'Focused add-on services that complement a core makeup booking',
        'services': [
            ('Eye Makeup Only', 'Focused eye makeup: eyeshadow, liner, and lashes'),
            ('Eyebrow Shaping', 'Eyebrow shaping using threading or waxing technique'),
            ('Eyebrow Tinting', 'Henna or dye tint to fill and define eyebrows'),
        ],
    },
]

LOCATION_TYPES = [
    ('Home Visit', 'Artist travels to the customer\'s home or preferred address'),
    ('In-Salon', 'Customer visits the artist\'s registered salon or studio'),
    ('On-Site Event', 'Artist attends the customer\'s event venue (wedding hall, banquet, etc.)'),
]

BOOKING_STATUSES = [
    ('pending', 'Booking request placed by customer, awaiting artist confirmation'),
    ('confirmed', 'Artist has accepted and confirmed the booking'),
    ('in_progress', 'Service is currently being delivered'),
    ('completed', 'Service successfully delivered and booking closed'),
    ('cancelled', 'Booking cancelled by customer or artist'),
    ('no_show', 'Customer did not show up / was not reachable at the scheduled time'),
]

PAYMENT_STATUSES = [
    ('pending', 'Payment not yet initiated'),
    ('paid', 'Full payment received successfully'),
    ('partially_refunded', 'Partial refund issued to the customer'),
    ('refunded', 'Full refund issued to the customer'),
    ('failed', 'Payment attempt failed or declined'),
]

APPROVAL_STATUSES = [
    ('pending', 'Artist profile submitted, awaiting admin review'),
    ('approved', 'Artist profile verified and approved to accept bookings'),
    ('rejected', 'Artist profile rejected; resubmission required with corrections'),
    ('suspended', 'Artist account temporarily suspended due to policy violation'),
]


class Command(BaseCommand):
    help = 'Seed core master data: service categories, sub-categories, location types, and status lookup tables'

    def handle(self, *_args, **_options):
        self._seed_service_categories()
        self._seed_location_types()
        self._seed_booking_statuses()
        self._seed_payment_statuses()
        self._seed_approval_statuses()
        self.stdout.write(self.style.SUCCESS('Core master data seeded successfully.'))

    def _seed_service_categories(self):
        count_cat = 0
        count_sub = 0
        for cat_data in CATEGORIES:
            cat, created = ServiceCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']},
            )
            if created:
                count_cat += 1
            for svc_name, svc_desc in cat_data['services']:
                _, sub_created = ServiceSubCategory.objects.get_or_create(
                    category=cat,
                    name=svc_name,
                    defaults={'description': svc_desc},
                )
                if sub_created:
                    count_sub += 1
        self.stdout.write(f'  Service categories: {count_cat} created')
        self.stdout.write(f'  Service sub-categories: {count_sub} created')

    def _seed_location_types(self):
        count = 0
        for name, desc in LOCATION_TYPES:
            _, created = LocationType.objects.get_or_create(name=name, defaults={'description': desc})
            if created:
                count += 1
        self.stdout.write(f'  Location types: {count} created')

    def _seed_booking_statuses(self):
        count = 0
        for name, desc in BOOKING_STATUSES:
            _, created = BookingStatus.objects.get_or_create(name=name, defaults={'description': desc})
            if created:
                count += 1
        self.stdout.write(f'  Booking statuses: {count} created')

    def _seed_payment_statuses(self):
        count = 0
        for name, desc in PAYMENT_STATUSES:
            _, created = PaymentStatus.objects.get_or_create(name=name, defaults={'description': desc})
            if created:
                count += 1
        self.stdout.write(f'  Payment statuses: {count} created')

    def _seed_approval_statuses(self):
        count = 0
        for name, desc in APPROVAL_STATUSES:
            _, created = ApprovalStatus.objects.get_or_create(name=name, defaults={'description': desc})
            if created:
                count += 1
        self.stdout.write(f'  Approval statuses: {count} created')
