from django.core.management.base import BaseCommand
from sunndari_apps.core.models import (
    ServiceCategory, ServiceSubCategory, LocationType,
    BookingStatus, PaymentStatus, ApprovalStatus,
)

CATEGORIES = [
    {
        'name': 'Bridal',
        'description': 'Complete bridal beauty packages for weddings and ceremonies',
        'services': [
            ('Bridal Makeup', 'Full bridal makeup with setting spray, includes skin prep and final look'),
            ('Engagement Makeup', 'Elegant makeup look for engagement ceremonies'),
            ('Reception Makeup', 'Glamorous makeup for wedding reception events'),
            ('Bridal Mehendi', 'Intricate full-hand and leg mehendi designs for brides'),
            ('Bridal Hairstyling', 'Elaborate bridal hairstyle including bun, braids, and hair accessories'),
            ('Dulha Grooming', 'Groom grooming package: facial, cleanup, and styling'),
        ],
    },
    {
        'name': 'Hair',
        'description': 'Professional haircut, colour, and treatment services',
        'services': [
            ('Haircut (Women)', 'Professional haircut for women including blow dry'),
            ('Haircut (Men)', 'Precision haircut for men with styling'),
            ('Hair Wash & Blow Dry', 'Shampoo, conditioning treatment, and blow dry'),
            ('Hair Colour (Global)', 'Full hair colour using ammonia-free professional colour'),
            ('Highlights & Balayage', 'Partial or full highlights / balayage technique for natural-looking colour'),
            ('Hair Smoothening', 'Semi-permanent smoothening treatment for frizz-free hair'),
            ('Keratin Treatment', 'Brazilian keratin treatment for smooth, shiny, manageable hair'),
            ('Hair Spa', 'Deep conditioning spa treatment with steam and massage'),
            ('Hair Bonding', 'Bond repair treatment (Olaplex / K18) for damaged and chemically-treated hair'),
        ],
    },
    {
        'name': 'Skin & Facial',
        'description': 'Facial treatments and skin care services',
        'services': [
            ('Basic Facial', 'Classic cleansing facial with steam, extraction, and moisturisation'),
            ('Gold Facial', '24K gold-infused facial for brightening and anti-ageing'),
            ('Diamond Facial', 'Diamond-tip microdermabrasion facial for deep exfoliation'),
            ('Detan Facial', 'De-tanning facial to remove sun tan and even skin tone'),
            ('Cleanup', 'Express cleanup for instant freshness: cleanser, scrub, mask, moisturiser'),
            ('Bleach', 'Herbal or cream bleach to lighten facial hair and brighten complexion'),
            ('Whitening Facial', 'Vitamin C brightening facial for radiant, glowing skin'),
            ('Anti-Ageing Facial', 'Collagen and peptide facial to reduce fine lines and wrinkles'),
        ],
    },
    {
        'name': 'Nail Art',
        'description': 'Manicure, pedicure, and nail extension services',
        'services': [
            ('Basic Manicure', 'Classic manicure: soak, cuticle care, filing, and polish'),
            ('Luxury Manicure', 'Spa manicure with scrub, mask, massage, and gel polish'),
            ('Gel Nails', 'UV/LED gel nail application for long-lasting shine'),
            ('Acrylic Nails', 'Acrylic nail extensions with gel polish overlay'),
            ('Basic Pedicure', 'Classic pedicure: soak, scrub, cuticle care, and polish'),
            ('Spa Pedicure', 'Relaxing spa pedicure with foot soak, callus removal, and massage'),
            ('Nail Art Design', 'Custom nail art designs including chrome, foil, and stamping'),
            ('Nail Extensions', 'Fiberglass or builder gel nail extensions for added length'),
        ],
    },
    {
        'name': 'Waxing & Threading',
        'description': 'Hair removal services for face and body',
        'services': [
            ('Full Body Wax', 'Complete body waxing from neck to toe using rica or chocolate wax'),
            ('Half Leg Wax', 'Waxing for lower legs (knee to ankle)'),
            ('Underarm Wax', 'Underarm hair removal with soothing wax'),
            ('Bikini Wax', 'Bikini line waxing with sensitive skin wax'),
            ('Eyebrow Threading', 'Precise eyebrow shaping with cotton thread'),
            ('Upper Lip Threading', 'Upper lip hair removal with threading'),
            ('Full Face Threading', 'Complete face threading including eyebrows, upper lip, chin, and cheeks'),
        ],
    },
    {
        'name': 'Mehendi',
        'description': 'Traditional and contemporary mehendi (henna) designs',
        'services': [
            ('Bridal Full Mehendi', 'Full hands and legs elaborate bridal mehendi with dulha motifs'),
            ('Dulha Mehendi', 'Groom mehendi for hands and feet with name and special designs'),
            ('Party Mehendi (Both Hands)', 'Festive mehendi designs for both hands up to wrists'),
            ('Festival Mehendi', 'Quick decorative mehendi for festivals: Eid, Karva Chauth, Teej'),
            ('Arabic Mehendi', 'Bold floral Arabic mehendi pattern for one hand'),
            ('Finger Mehendi', 'Minimal finger and knuckle mehendi for modern brides'),
        ],
    },
    {
        'name': 'Massage & Body',
        'description': 'Relaxation and therapeutic massage treatments',
        'services': [
            ('Swedish Massage', 'Classic relaxation massage using long gliding strokes'),
            ('Deep Tissue Massage', 'Therapeutic massage targeting deep muscle layers for pain relief'),
            ('Ayurvedic Abhyanga', 'Traditional Ayurvedic full-body oil massage with herbal oils'),
            ('Head & Scalp Massage', 'Relaxing head massage using coconut or argan oil'),
            ('Foot Reflexology', 'Pressure-point foot massage targeting reflex zones'),
            ('Body Polishing', 'Full-body exfoliation and hydration treatment for silky smooth skin'),
            ('Body Scrub', 'Coffee or salt scrub for exfoliation and improved circulation'),
        ],
    },
    {
        'name': 'Makeup',
        'description': 'Professional makeup services for all occasions',
        'services': [
            ('Party Makeup', 'Glamorous party-ready makeup using MAC / KRYOLAN products'),
            ('HD Makeup', 'High-definition makeup that looks flawless on camera'),
            ('Airbrush Makeup', 'Airbrush foundation makeup for a seamless, long-lasting finish'),
            ('Eye Makeup Only', 'Focused eye makeup: eyeshadow, liner, and lashes'),
            ('Natural / Dewy Makeup', 'Light, skin-like makeup for everyday or daytime events'),
        ],
    },
    {
        'name': 'Eyebrow & Lash',
        'description': 'Eyebrow shaping and eyelash enhancement services',
        'services': [
            ('Eyebrow Shaping', 'Eyebrow shaping using threading or waxing technique'),
            ('Eyebrow Tinting', 'Henna or dye tint to fill and define eyebrows'),
            ('Eyelash Extension (Classic)', 'One-to-one lash extension application for natural volume'),
            ('Eyelash Extension (Volume)', 'Multi-lash fan extension for dramatic, full volume look'),
            ('Lash Lift & Tint', 'Semi-permanent lash curl with tint for no-mascara look'),
            ('Henna Brows (Microblading)', 'Semi-permanent henna brow tattoo for defined, filled arches'),
        ],
    },
    {
        'name': 'Pre-Bridal Packages',
        'description': 'Curated multi-session beauty packages to prepare brides for their big day',
        'services': [
            ('Pre-Bridal Basic (4 Sessions)', 'Facial, cleanup, waxing, and threading across 4 sessions'),
            ('Pre-Bridal Silver (6 Sessions)', 'Gold facial, body polishing, detan, waxing, eyebrows across 6 sessions'),
            ('Pre-Bridal Gold (8 Sessions)', 'Advanced facials, hair spa, nail service, body massage across 8 sessions'),
            ('Pre-Bridal Platinum (12 Sessions)', 'Complete transformation: all treatments, hair colour, skin booster shots across 12 sessions'),
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
