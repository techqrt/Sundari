"""Every model in the Django admin must show a useful list: real columns (names, statuses, amounts, dates), working
search / filters / sorting, no per-row queries, and no personal or secret data in a list."""
from datetime import timedelta, time
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sunndari_apps.artists.models import (
    ArtistAvailabilityBlock, ArtistAvailabilitySchedule, ArtistClientNote, ArtistDocument, ArtistLocationPreference,
    ArtistPayoutAccount, ArtistReviewFeedback, ArtistServiceArea, ArtistServiceOffering, ArtistSpeciality, BrandRequest,
    PackageAddOn, PackageInclusion, Portfolio,
)
from sunndari_apps.authentication.models import User
from sunndari_apps.chat.models import Conversation, Message
from sunndari_apps.core.models import ApprovalStatus, ServiceCategory, ServiceSubCategory
from sunndari_apps.customers.models import Booking, BookingAddOn, BookingReschedule, CustomerReview, Review
from sunndari_apps.help_center.models import SupportConversation, SupportMessage, SupportTicket, SupportTicketAttachment
from sunndari_apps.notifications.models.notification import Notification
from sunndari_apps.payments.models import Payment

from tests.test_customers import (
    make_artist, make_booking, make_customer, make_location_type, make_package, make_paid_payment, make_sub_category,
    next_weekday, seed_booking_statuses, seed_payment_statuses,
)

OUR_APPS = {'artists', 'authentication', 'chat', 'core', 'customers', 'help_center', 'notifications', 'payments', 'users', 'wallet'}


def our_models():
    return sorted(
        ((model, model_admin) for model, model_admin in admin.site._registry.items() if model._meta.app_label in OUR_APPS),
        key=lambda pair: (pair[0]._meta.app_label, pair[0].__name__))


class EveryModelHasUsefulColumnsTest(TestCase):
    """Structural: nothing is left showing only 'Name (Artist #29)'."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser(username='root', email='r@x.com', password='x'))

    def test_no_model_is_left_with_only_its_name_as_a_column(self):
        bare = [f'{m._meta.app_label}.{m.__name__}' for m, a in our_models() if len([c for c in a.list_display if c != '__str__']) < 2]
        self.assertEqual(bare, [], 'these admin lists still show almost nothing')

    def test_every_list_page_sorts_filters_and_searches_without_error(self):
        problems = []
        for model, model_admin in our_models():
            url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
            requests = [('plain', {})] + [('search', {'q': 'asha'})] + [(f'sort column {i}', {'o': str(i)}) for i in range(1, len(model_admin.list_display) + 1)] \
                + [(f'sort desc {i}', {'o': f'-{i}'}) for i in range(1, len(model_admin.list_display) + 1)]
            for label, params in requests:
                response = self.client.get(url, params)
                if response.status_code != 200:
                    problems.append(f'{model.__name__} {label}: HTTP {response.status_code}')
        self.assertEqual(problems, [])

    def test_every_declared_filter_option_can_be_applied(self):
        problems = []
        for model, model_admin in our_models():
            url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
            page = self.client.get(url)
            for spec in page.context['cl'].filter_specs if page.status_code == 200 else []:
                for choice in spec.choices(page.context['cl']):
                    query = choice.get('query_string')
                    if query and choice.get('display') != 'All':
                        response = self.client.get(url + query)
                        if response.status_code != 200:
                            problems.append(f'{model.__name__} filter {spec.title} = {choice.get("display")}: HTTP {response.status_code}')
        self.assertEqual(problems, [])


class PopulatedListsShowPeopleAndValuesTest(TestCase):
    """Behaviour: with real rows, each list shows readable values - and never a secret."""

    SECRETS = {'ID number': '123409876543', 'bank account': '5550001112223334', 'upi id': 'asha.private@upi',
               'booking otp': '848381', 'start pin': '717273', 'completion pin': '626364', 'document file': 'kyc/secret-aadhaar.png'}

    def setUp(self):
        seed_booking_statuses()
        seed_payment_statuses()
        self.client.force_login(get_user_model().objects.create_superuser(username='root', email='r@x.com', password='x'))
        self.artist_client, self.artist_user, self.profile = make_artist(phone_number='+919700000001', name='Asha Verma')
        self.cust_client, self.customer = make_customer(phone_number='+919700000002', name='Rohan Mehta')
        category = ServiceCategory.objects.create(name='Makeup')
        self.sub = ServiceSubCategory.objects.create(category=category, name='Bridal Makeup')
        self.package = make_package(self.profile, sub_category=self.sub, price=2500, name='Bridal Glow Package')
        self.location = make_location_type()
        self.date = next_weekday(2)
        self.booking = make_booking(self.customer, self.profile, self.package, self.location, self.date, '10:00:00', '11:00:00')
        Booking.objects.filter(pk=self.booking.pk).update(booking_otp=848381, start_service_pin=717273, completion_pin=626364)
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'ok'})
        ArtistAvailabilityBlock.objects.create(artist=self.profile, block_date=self.date, note='Family function')
        ArtistAvailabilitySchedule.objects.create(artist=self.profile, day_of_week=2, start_time=time(9), end_time=time(18), location_type=self.location)
        ArtistClientNote.objects.create(artist=self.profile, customer=self.customer, note='Prefers a natural look and arrives early')
        ArtistDocument.objects.create(artist=self.profile, document_type='id_proof', id_type='aadhaar', document_number=self.SECRETS['ID number'],
                                      file=self.SECRETS['document file'], verification_status=approved)
        ArtistLocationPreference.objects.create(artist=self.profile, location_type=self.location)
        ArtistPayoutAccount.objects.create(artist=self.profile, account_holder_name='Asha Verma', bank_account_number=self.SECRETS['bank account'],
                                           ifsc_code='HDFC0001234', upi_id=self.SECRETS['upi id'], verification_status=approved)
        ArtistReviewFeedback.objects.create(artist=self.profile, admin_user=User.objects.create(phone_number='+919700000009', role='admin', name='Priya Admin'),
                                            decision='approved', message='All documents verified, welcome aboard.')
        ArtistServiceArea.objects.create(artist=self.profile, city='Lucknow', travel_charge_type='per_visit', charge_amount=Decimal('250'))
        ArtistServiceOffering.objects.create(artist=self.profile, sub_category=self.sub, custom_price=Decimal('2600'))
        ArtistSpeciality.objects.create(artist=self.profile, sub_category=self.sub)
        BrandRequest.objects.create(artist=self.profile, name='Huda Beauty')
        self.addon = PackageAddOn.objects.create(artist=self.profile, name='Hair Styling', price=Decimal('500'), duration_minutes=30)
        PackageInclusion.objects.create(package=self.package, inclusion_text='HD foundation and setting spray', order=1)
        Portfolio.objects.create(artist=self.profile, file='portfolios/a.jpg', media_type='image', sub_category=self.sub, caption='Bridal look', approval_status=approved)
        BookingAddOn.objects.create(booking=self.booking, addon=self.addon, name='Hair Styling', price=Decimal('500'), duration_minutes=30)
        BookingReschedule.objects.create(
            booking=self.booking, requested_by=self.artist_user, previous_date=self.date, previous_start_time=time(10), previous_end_time=time(11),
            proposed_date=self.date + timedelta(days=1), proposed_start_time=time(12), proposed_end_time=time(13), expires_at=timezone.now() + timedelta(days=1))
        CustomerReview.objects.create(booking=self.booking, artist=self.profile, customer=self.customer, rating=4, comment='Punctual and polite')
        Review.objects.create(booking=self.booking, customer=self.customer, artist=self.profile, rating=5, comment='Wonderful bridal makeup', reply='Thank you Rohan!')
        make_paid_payment(self.booking)
        Payment.objects.filter(booking=self.booking).update(gateway='razorpay', gateway_order_id='order_ABC123', gateway_payment_id='pay_XYZ789')
        Notification.objects.create(user=self.customer, type='booking_confirmed', title='Booking confirmed', message='See you on the day')
        conversation = Conversation.objects.create(booking=self.booking)
        Message.objects.create(conversation=conversation, sender=self.customer, content='Could you bring a lash kit please')
        support = SupportConversation.objects.create(customer=self.customer, subject='Refund question')
        SupportMessage.objects.create(conversation=support, sender=self.customer, content='When will my refund arrive?')
        ticket = SupportTicket.objects.create(user=self.customer, issue_type='payment', subject='Charged twice', description='Two charges on my card')
        SupportTicketAttachment.objects.create(ticket=ticket, file='support_tickets/shot.png')

    def page(self, model):
        response = self.client.get(reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist'))
        self.assertEqual(response.status_code, 200, model.__name__)
        return response.content.decode()

    def test_every_populated_list_shows_a_row_with_readable_people_and_values(self):
        expectations = {
            ArtistAvailabilityBlock: ['Asha Verma', 'Family function'], ArtistAvailabilitySchedule: ['Asha Verma', 'Home Visit'],
            ArtistClientNote: ['Asha Verma', 'Rohan Mehta', 'Prefers a natural look'], ArtistDocument: ['Asha Verma', 'id_proof', 'aadhaar'],
            ArtistLocationPreference: ['Asha Verma', 'Home Visit'], ArtistPayoutAccount: ['Asha Verma'],
            ArtistReviewFeedback: ['Asha Verma', 'Priya Admin', 'All documents verified'],
            ArtistServiceArea: ['Asha Verma', 'Lucknow', 'per_visit'], ArtistServiceOffering: ['Asha Verma', 'Bridal Makeup'],
            ArtistSpeciality: ['Asha Verma', 'Bridal Makeup'], BrandRequest: ['Asha Verma', 'Huda Beauty'],
            PackageAddOn: ['Hair Styling', 'Asha Verma'], PackageInclusion: ['HD foundation', 'Asha Verma', 'Bridal Glow Package'],
            Portfolio: ['Asha Verma', 'Bridal Makeup'], Booking: ['Rohan Mehta', 'Asha Verma', 'pending', '2500'],
            BookingAddOn: ['Hair Styling'], BookingReschedule: ['Asha Verma', 'pending'],
            CustomerReview: ['Asha Verma', 'Rohan Mehta', 'Punctual and polite'], Review: ['Rohan Mehta', 'Asha Verma', 'Wonderful bridal makeup'],
            Payment: ['Rohan Mehta', 'Asha Verma', 'razorpay', '2500'], Notification: ['Rohan Mehta', 'booking_confirmed', 'Booking confirmed'],
            Conversation: ['Rohan Mehta', 'Asha Verma'], Message: ['Rohan Mehta', 'Could you bring a lash kit'],
            SupportMessage: ['Rohan Mehta', 'When will my refund arrive'], SupportTicket: ['Rohan Mehta', 'Charged twice', 'payment'],
            SupportTicketAttachment: ['Charged twice'], SupportConversation: ['Refund question'],
        }
        from sunndari_apps.artists.models import ArtistProfile, PricingPackage
        expectations[ArtistProfile] = ['Asha Verma', '+919700000001']
        expectations[PricingPackage] = ['Bridal Glow Package', 'Asha Verma', 'Bridal Makeup']
        missing = []
        for model, wanted in expectations.items():
            html = self.page(model)
            missing += [f'{model.__name__}: "{text}" not shown' for text in wanted if text not in html]
        self.assertEqual(missing, [])

    def test_no_list_shows_an_id_number_bank_detail_otp_or_pin(self):
        leaks = []
        for model, _ in our_models():
            html = self.page(model)
            leaks += [f'{model.__name__} shows {what}' for what, value in self.SECRETS.items() if value in html]
        self.assertEqual(leaks, [])

    def test_the_row_labels_are_not_just_numbers(self):
        # The screenshot problem: every row said "id_proof (Artist #29)" and nothing else.
        html = self.page(ArtistDocument)
        self.assertIn('Asha Verma', html)
        self.assertIn('Verification status', html)
        self.assertIn('Created at', html)


class ListsDoNotQueryPerRowTest(TestCase):

    def test_list_query_counts_do_not_grow_with_the_number_of_rows(self):
        seed_booking_statuses()
        seed_payment_statuses()
        client = self.client
        client.force_login(get_user_model().objects.create_superuser(username='root', email='r@x.com', password='x'))
        location = make_location_type()
        sub = make_sub_category()

        def add_rows(n, start):
            for i in range(start, start + n):
                _, _, profile = make_artist(phone_number=f'+9198{i:08d}', name=f'Artist {i}')
                _, customer = make_customer(phone_number=f'+9197{i:08d}', name=f'Customer {i}')
                package = make_package(profile, sub_category=sub, price=1500, name=f'Package {i}')
                booking = make_booking(customer, profile, package, location, next_weekday(2), '10:00:00', '11:00:00')
                make_paid_payment(booking)
                Notification.objects.create(user=customer, type='booking_confirmed', title=f'Hello {i}', message='m')
                PackageAddOn.objects.create(artist=profile, name=f'Addon {i}', price=Decimal('100'), duration_minutes=15)

        def counts():
            result = {}
            for model in (Booking, Payment, Notification, PackageAddOn):
                url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
                from sunndari_apps.artists.models import PricingPackage
                with CaptureQueriesContext(connection) as ctx:
                    self.assertEqual(client.get(url).status_code, 200)
                result[model.__name__] = len(ctx)
            from sunndari_apps.artists.models import PricingPackage
            with CaptureQueriesContext(connection) as ctx:
                client.get(reverse('admin:artists_pricingpackage_changelist'))
            result['PricingPackage'] = len(ctx)
            return result

        add_rows(3, 100)
        few = counts()
        add_rows(15, 200)
        many = counts()
        self.assertEqual(few, many, f'a list is querying once per row: {few} vs {many}')
