import io
import tempfile
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistServiceOffering, ArtistLocationPreference,
    Portfolio, PricingPackage, PackageInclusion,
    ArtistAvailabilitySchedule, ArtistAvailabilityBlock,
    ArtistDocument, ArtistPayoutAccount,
)
from sunndari_apps.core.models import ServiceSubCategory, ServiceCategory, LocationType, ApprovalStatus
from sunndari_apps.users.models.customer_address import CustomerAddress


# ─── Helpers ──────────────────────────────────────────────────────────────────

ID_PROOF_FORM = {'document_type': 'id_proof', 'id_type': 'passport', 'document_number': 'K1234567'}


def make_image_bytes(image_format='PNG'):
    """A genuine, decodable image — uploads are now content-validated, so opaque bytes
    labelled image/jpeg are (correctly) rejected."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (200, 100, 50)).save(buffer, format=image_format)
    return buffer.getvalue()


def make_user(phone_number='+919876543210', role='artist', name='Test Artist'):
    return User.objects.create(phone_number=phone_number, role=role, name=name)


def make_authenticated_client(phone_number='+919876543210', role='artist'):
    user = make_user(phone_number=phone_number, role=role)
    if role == 'artist':
        ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        ArtistProfile.create_for_user(user_id=user.user_id)
    token = generate_jwt_token(user)
    user.access_token = token
    user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client, user


def make_category(name='Hair'):
    return ServiceCategory.objects.create(name=name)


def make_sub_category(category=None, name='Haircut'):
    if category is None:
        category = make_category()
    return ServiceSubCategory.objects.create(category=category, name=name)


def make_location_type(name='Home Visit'):
    return LocationType.objects.create(name=name)


def make_package(artist: ArtistProfile, sub_category=None, name='Basic Package', price=1000, duration=60):
    if sub_category is None:
        sub_category = make_sub_category()
    pkg = PricingPackage()
    pkg.create(
        artist_id=artist.artist_id,
        sub_category_id=sub_category.sub_category_id,
        name=name,
        price=price,
        duration_minutes=duration,
    )
    return pkg


def get_artist_profile(user):
    return ArtistProfile.objects.get(user_id=user.user_id)


def make_address(user, city='Lucknow'):
    address = CustomerAddress()
    address_id = address.create(user_id=user.user_id, address_line_1='12 MG Road', city=city, pin_code='226001')
    return address_id


def complete_onboarding_steps(client, user):
    """Drives every onboarding step to completion via the real HTTP endpoints
    (reusing the pre-existing service/package/location/availability APIs), so
    onboarding status/submit tests exercise the same path a real artist would."""
    address_id = make_address(user)
    sub = make_sub_category()
    location_type = make_location_type()
    client.put('/artists/profile/update/', {
        'bio': 'Experienced bridal makeup artist', 'city': 'Lucknow', 'base_address_id': address_id,
        'display_name': 'Glam by Test', 'date_of_birth': '1995-05-20', 'profile_type': 'freelance',
    }, format='json')
    client.post('/artists/portfolio/create/', {
        'media_type': 'image', 'sub_category_id': sub.sub_category_id, 'is_work_sample': 'true',
        'file': SimpleUploadedFile('work.png', make_image_bytes('PNG'), content_type='image/png'),
    }, format='multipart')
    client.post('/artists/services/add/', {'sub_category_id': sub.sub_category_id}, format='json')
    client.post('/artists/packages/create/', {
        'sub_category_id': sub.sub_category_id, 'name': 'Bridal Package', 'price': '3000.00', 'duration_minutes': 60,
    }, format='json')
    client.post('/artists/locations/add/', {'location_type_id': location_type.location_type_id}, format='json')
    client.post('/artists/availability/schedule/set/', {
        'day_of_week': 0, 'start_time': '09:00:00', 'end_time': '18:00:00',
    }, format='json')
    client.post('/artists/documents/create/', {
        **ID_PROOF_FORM,
        'file': SimpleUploadedFile('id.png', make_image_bytes('PNG'), content_type='image/png'),
    }, format='multipart')
    client.put('/artists/payout_account/set/', {
        'account_holder_name': 'Test Artist', 'bank_account_number': '111122223333', 'ifsc_code': 'HDFC0001234',
    }, format='json')
    client.put('/artists/profile/agreement/accept/', {}, format='json')
    return get_artist_profile(user)


# ─── ArtistProfile Auto-Creation ──────────────────────────────────────────────

class ArtistProfileAutoCreateTest(TestCase):

    def test_artist_registration_creates_profile(self):
        ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        user = User.objects.create(phone_number='+919000000001', role='artist')
        ArtistProfile.create_for_user(user_id=user.user_id)
        self.assertTrue(ArtistProfile.objects.filter(user_id=user.user_id).exists())

    def test_customer_has_no_artist_profile(self):
        user = User.objects.create(phone_number='+919000000002', role='customer')
        self.assertFalse(ArtistProfile.objects.filter(user_id=user.user_id).exists())

    def test_artist_profile_has_pending_status(self):
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        user = User.objects.create(phone_number='+919000000003', role='artist')
        ArtistProfile.create_for_user(user_id=user.user_id)
        profile = ArtistProfile.objects.get(user_id=user.user_id)
        self.assertEqual(profile.approval_status_id, pending.status_id)

    def test_auth_registration_creates_artist_profile(self):
        ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        client = APIClient()
        resp = client.post('/auth/register/', {
            'name': 'New Artist',
            'phone_number': '+919111111111',
            'password': 'SecurePass123!',
            'role': 'artist',
        })
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone_number='+919111111111')
        self.assertTrue(ArtistProfile.objects.filter(user_id=user.user_id).exists())

    def test_auth_registration_customer_no_artist_profile(self):
        client = APIClient()
        resp = client.post('/auth/register/', {
            'name': 'New Customer',
            'phone_number': '+919222222222',
            'password': 'SecurePass123!',
            'role': 'customer',
        })
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone_number='+919222222222')
        self.assertFalse(ArtistProfile.objects.filter(user_id=user.user_id).exists())


# ─── Artist Profile Get/Update ────────────────────────────────────────────────

class ArtistProfileGetTest(TestCase):
    url = '/artists/profile/get/'

    def test_get_own_profile_returns_200(self):
        client, user = make_authenticated_client()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['status'])
        self.assertIn('artistId', resp.data['data'])

    def test_get_profile_by_artist_id(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        resp = client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['artistId'], profile.artist_id)

    def test_get_nonexistent_artist_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.get(self.url, {'artist_id': 99999})
        self.assertEqual(resp.status_code, 400)

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def _approve(self, user):
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ArtistProfile.objects.filter(user_id=user.user_id).update(
            approval_status=approved, rejection_reason='internal note',
        )
        return get_artist_profile(user)

    def test_other_user_sees_only_public_fields_of_approved_artist(self):
        _, artist_user = make_authenticated_client(phone_number='+919000000310')
        profile = self._approve(artist_user)
        customer_client, _ = make_authenticated_client(phone_number='+919000000311', role='customer')
        resp = customer_client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        self.assertEqual(data['artistId'], profile.artist_id)
        for hidden in ('commissionRate', 'approvalStatusId', 'rejectionReason', 'termsAcceptedAt',
                       'submittedForReviewAt', 'baseAddressId'):
            self.assertNotIn(hidden, data)

    def test_other_user_cannot_request_internal_columns(self):
        _, artist_user = make_authenticated_client(phone_number='+919000000312')
        profile = self._approve(artist_user)
        other_client, _ = make_authenticated_client(phone_number='+919000000313')
        resp = other_client.get(self.url, {'artist_id': profile.artist_id, 'values': 'artistId,commissionRate'})
        self.assertEqual(resp.status_code, 400)

    def test_other_user_cannot_see_unapproved_artist(self):
        _, artist_user = make_authenticated_client(phone_number='+919000000314')
        profile = get_artist_profile(artist_user)
        other_client, _ = make_authenticated_client(phone_number='+919000000315')
        resp = other_client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.status_code, 400)

    def test_own_profile_still_returns_internal_fields(self):
        client, user = make_authenticated_client(phone_number='+919000000316')
        profile = self._approve(user)
        resp = client.get(self.url, {'artist_id': profile.artist_id})
        self.assertEqual(resp.data['data']['commissionRate'], '10.00')
        self.assertEqual(resp.data['data']['rejectionReason'], 'internal note')


class ArtistProfileUpdateTest(TestCase):
    url = '/artists/profile/update/'

    def test_update_bio_returns_200(self):
        client, user = make_authenticated_client()
        resp = client.put(self.url, {'bio': 'Expert in bridal makeup'})
        self.assertEqual(resp.status_code, 200)
        profile = get_artist_profile(user)
        self.assertEqual(profile.bio, 'Expert in bridal makeup')

    def test_update_city_does_not_reset_approval(self):
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        approved = ApprovalStatus.objects.get(name='approved')
        profile.approval_status = approved
        profile.save()

        resp = client.put(self.url, {'city': 'Mumbai'})
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, approved.status_id)

    def test_update_bio_no_re_approval(self):
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        approved = ApprovalStatus.objects.get(name='approved')
        profile.approval_status = approved
        profile.save()

        resp = client.put(self.url, {'bio': 'Just bio update'})
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, approved.status_id)

    def test_update_multiple_fields_no_re_approval(self):
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        approved = ApprovalStatus.objects.get(name='approved')
        profile.approval_status = approved
        profile.save()

        resp = client.put(self.url, {
            'bio': 'I am a professional makeup artist',
            'years_experience': 3,
            'city': 'Bhiwani',
        })
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, approved.status_id)
        self.assertEqual(profile.bio, 'I am a professional makeup artist')
        self.assertEqual(profile.years_experience, 3)
        self.assertEqual(profile.city, 'Bhiwani')

    def test_update_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.put(self.url, {'bio': 'Hacker'})
        self.assertEqual(resp.status_code, 401)


# ─── Artist Services ──────────────────────────────────────────────────────────

class ArtistServiceOfferingTest(TestCase):
    add_url = '/artists/services/add/'
    remove_url = '/artists/services/remove/'
    get_all_url = '/artists/services/get_all/'

    def test_add_service_returns_201(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.add_url, {'sub_category_id': sub.sub_category_id})
        self.assertEqual(resp.status_code, 201)
        profile = get_artist_profile(user)
        self.assertTrue(ArtistServiceOffering.exists(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id))

    def test_add_service_with_custom_price(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.add_url, {'sub_category_id': sub.sub_category_id, 'custom_price': '2500.00'})
        self.assertEqual(resp.status_code, 201)

    def test_add_service_does_not_demote_approved_artist(self):
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        profile.approval_status = approved
        profile.submitted_for_review_at = timezone.now()
        profile.save()

        sub = make_sub_category()
        resp = client.post(self.add_url, {'sub_category_id': sub.sub_category_id})
        self.assertEqual(resp.status_code, 201)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, approved.status_id)
        self.assertIsNotNone(profile.submitted_for_review_at)

    def test_remove_service_does_not_demote_approved_artist(self):
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        ArtistServiceOffering.add(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id)
        profile.approval_status = approved
        profile.save()

        resp = client.delete(f'{self.remove_url}?sub_category_id={sub.sub_category_id}')
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, approved.status_id)

    def test_remove_service_returns_200(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        profile = get_artist_profile(user)
        ArtistServiceOffering.add(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id)
        resp = client.delete(f'{self.remove_url}?sub_category_id={sub.sub_category_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ArtistServiceOffering.exists(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id))

    def test_get_all_services_returns_200(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        profile = get_artist_profile(user)
        ArtistServiceOffering.add(artist_id=profile.artist_id, sub_category_id=sub.sub_category_id)
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']), 1)


# ─── Artist Location Preferences ──────────────────────────────────────────────

class ArtistLocationPreferenceTest(TestCase):
    add_url = '/artists/locations/add/'
    remove_url = '/artists/locations/remove/'
    get_all_url = '/artists/locations/get_all/'

    def test_add_location_returns_201(self):
        client, user = make_authenticated_client()
        lt = make_location_type()
        resp = client.post(self.add_url, {'location_type_id': lt.location_type_id})
        self.assertEqual(resp.status_code, 201)

    def test_remove_location_returns_200(self):
        client, user = make_authenticated_client()
        lt = make_location_type()
        profile = get_artist_profile(user)
        ArtistLocationPreference.add(artist_id=profile.artist_id, location_type_id=lt.location_type_id)
        resp = client.delete(f'{self.remove_url}?location_type_id={lt.location_type_id}')
        self.assertEqual(resp.status_code, 200)

    def test_get_all_locations_returns_200(self):
        client, user = make_authenticated_client()
        lt = make_location_type()
        profile = get_artist_profile(user)
        ArtistLocationPreference.add(artist_id=profile.artist_id, location_type_id=lt.location_type_id)
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']), 1)


# ─── Portfolio ────────────────────────────────────────────────────────────────

class PortfolioCreateTest(TestCase):
    url = '/artists/portfolio/create/'

    def _make_file(self, name='test.jpg', content=None):
        return SimpleUploadedFile(name, content or make_image_bytes('JPEG'), content_type='image/jpeg')

    def test_create_portfolio_returns_201(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.url, {
            'media_type': 'image',
            'sub_category_id': sub.sub_category_id,
            'caption': 'My bridal work',
            'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('portfolio_id', resp.data['data'])

    def test_create_beyond_20_returns_400(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        profile = get_artist_profile(user)
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        for i in range(20):
            Portfolio.objects.create(
                artist=profile,
                file=f'portfolios/test_{i}.jpg',
                media_type='image',
                sub_category=sub,
                approval_status=pending,
                is_active=True,
            )
        resp = client.post(self.url, {
            'media_type': 'image',
            'sub_category_id': sub.sub_category_id,
            'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_create_unauthenticated_returns_401(self):
        client = APIClient()
        sub = make_sub_category()
        resp = client.post(self.url, {
            'media_type': 'image',
            'sub_category_id': sub.sub_category_id,
            'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 401)


class PortfolioGetUpdateDeleteTest(TestCase):
    get_url = '/artists/portfolio/get/'
    update_url = '/artists/portfolio/update/'
    delete_url = '/artists/portfolio/delete/'
    get_all_url = '/artists/portfolio/get_all/'

    def _make_portfolio(self, profile, sub):
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        return Portfolio.objects.create(
            artist=profile, file='portfolios/test.jpg', media_type='image',
            sub_category=sub, approval_status=pending, is_active=True,
        )

    def test_get_portfolio_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        p = self._make_portfolio(profile, sub)
        resp = client.get(self.get_url, {'portfolio_id': p.portfolio_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['portfolioId'], p.portfolio_id)

    def test_get_another_artists_portfolio_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919000000010')
        _, user2 = make_authenticated_client(phone_number='+919000000011')
        profile2 = get_artist_profile(user2)
        sub = make_sub_category()
        p = self._make_portfolio(profile2, sub)
        resp = client.get(self.get_url, {'portfolio_id': p.portfolio_id})
        self.assertEqual(resp.status_code, 400)

    def test_update_caption_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        p = self._make_portfolio(profile, sub)
        resp = client.put(self.update_url, {'portfolio_id': p.portfolio_id, 'caption': 'Updated caption'})
        self.assertEqual(resp.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.caption, 'Updated caption')

    def test_delete_own_portfolio_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        p = self._make_portfolio(profile, sub)
        resp = client.delete(f'{self.delete_url}?portfolio_id={p.portfolio_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Portfolio.objects.filter(portfolio_id=p.portfolio_id).exists())

    def test_get_all_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        self._make_portfolio(profile, sub)
        self._make_portfolio(profile, sub)
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 2)


# ─── Pricing Packages ─────────────────────────────────────────────────────────

class PricingPackageTest(TestCase):
    create_url = '/artists/packages/create/'
    update_url = '/artists/packages/update/'
    delete_url = '/artists/packages/delete/'
    get_url = '/artists/packages/get/'
    get_all_url = '/artists/packages/get_all/'

    def test_create_package_returns_201(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.create_url, {
            'sub_category_id': sub.sub_category_id,
            'name': 'Bridal Package',
            'price': '5000.00',
            'duration_minutes': 180,
            'inclusions': ['HD Makeup', 'Hair Setting', 'Touch-up Kit'],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('package_id', resp.data['data'])

    def test_create_package_price_below_500_returns_400(self):
        client, _ = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.create_url, {
            'sub_category_id': sub.sub_category_id,
            'name': 'Cheap Package',
            'price': '499.00',
            'duration_minutes': 30,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_create_package_stores_inclusions(self):
        client, user = make_authenticated_client()
        sub = make_sub_category()
        resp = client.post(self.create_url, {
            'sub_category_id': sub.sub_category_id,
            'name': 'Test Package',
            'price': '1500.00',
            'duration_minutes': 90,
            'inclusions': ['Inclusion 1', 'Inclusion 2'],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        pkg_id = resp.data['data']['package_id']
        inclusions = PackageInclusion.get_for_package(package_id=pkg_id)
        self.assertEqual(len(inclusions), 2)

    def test_delete_last_active_package_returns_400(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        pkg = make_package(profile, sub)
        resp = client.delete(f'{self.delete_url}?package_id={pkg.package_id}')
        self.assertEqual(resp.status_code, 400)

    def test_delete_one_of_two_packages_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        pkg1 = make_package(profile, sub, name='Package 1')
        pkg2 = make_package(profile, sub, name='Package 2')
        resp = client.delete(f'{self.delete_url}?package_id={pkg1.package_id}')
        self.assertEqual(resp.status_code, 200)

    def test_get_package_with_inclusions(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        pkg = make_package(profile, sub)
        PackageInclusion.set_for_package(package_id=pkg.package_id, inclusions=['Inc 1', 'Inc 2'])
        resp = client.get(self.get_url, {'package_id': pkg.package_id})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('inclusions', resp.data['data'])
        self.assertEqual(len(resp.data['data']['inclusions']), 2)

    def test_get_all_packages_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        make_package(profile, sub, name='Pkg 1')
        make_package(profile, sub, name='Pkg 2')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 2)

    def test_update_package_price_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        sub = make_sub_category()
        pkg = make_package(profile, sub)
        resp = client.put(self.update_url, {
            'package_id': pkg.package_id,
            'price': '7500.00',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        pkg.refresh_from_db()
        self.assertEqual(float(pkg.price), 7500.00)


# ─── Availability Schedule ────────────────────────────────────────────────────

class AvailabilityScheduleTest(TestCase):
    set_url = '/artists/availability/schedule/set/'
    remove_url = '/artists/availability/schedule/remove/'
    get_all_url = '/artists/availability/schedule/get_all/'

    def test_set_schedule_returns_200(self):
        client, user = make_authenticated_client()
        resp = client.post(self.set_url, {
            'day_of_week': 1,
            'start_time': '09:00:00',
            'end_time': '18:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        profile = get_artist_profile(user)
        self.assertTrue(ArtistAvailabilitySchedule.objects.filter(artist=profile, day_of_week=1).exists())

    def test_set_schedule_replaces_existing(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        ArtistAvailabilitySchedule.objects.create(
            artist=profile, day_of_week=1, start_time='09:00', end_time='17:00'
        )
        resp = client.post(self.set_url, {
            'day_of_week': 1,
            'start_time': '10:00:00',
            'end_time': '19:00:00',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        slot = ArtistAvailabilitySchedule.objects.get(artist=profile, day_of_week=1)
        self.assertEqual(str(slot.start_time), '10:00:00')

    def test_remove_schedule_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        ArtistAvailabilitySchedule.objects.create(
            artist=profile, day_of_week=2, start_time='09:00', end_time='17:00'
        )
        resp = client.delete(f'{self.remove_url}?day_of_week=2')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ArtistAvailabilitySchedule.objects.filter(artist=profile, day_of_week=2).exists())

    def test_get_all_schedules_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        ArtistAvailabilitySchedule.objects.create(artist=profile, day_of_week=0, start_time='09:00', end_time='17:00')
        ArtistAvailabilitySchedule.objects.create(artist=profile, day_of_week=5, start_time='10:00', end_time='16:00')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']), 2)


# ─── Availability Blocks ──────────────────────────────────────────────────────

class AvailabilityBlockTest(TestCase):
    add_url = '/artists/availability/block/add/'
    remove_url = '/artists/availability/block/remove/'
    get_all_url = '/artists/availability/block/get_all/'

    def test_add_block_returns_201(self):
        client, user = make_authenticated_client()
        resp = client.post(self.add_url, {'block_date': '2026-12-25', 'note': 'Christmas'}, format='json')
        self.assertEqual(resp.status_code, 201)
        profile = get_artist_profile(user)
        self.assertTrue(ArtistAvailabilityBlock.objects.filter(artist=profile, block_date='2026-12-25').exists())

    def test_add_duplicate_block_is_idempotent(self):
        client, _ = make_authenticated_client()
        client.post(self.add_url, {'block_date': '2026-12-26'}, format='json')
        resp = client.post(self.add_url, {'block_date': '2026-12-26'}, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_remove_block_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        ArtistAvailabilityBlock.add(artist_id=profile.artist_id, block_date='2026-11-01')
        resp = client.delete(f'{self.remove_url}?block_date=2026-11-01')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ArtistAvailabilityBlock.objects.filter(artist=profile, block_date='2026-11-01').exists())

    def test_get_all_blocks_returns_200(self):
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        ArtistAvailabilityBlock.add(artist_id=profile.artist_id, block_date='2026-10-01')
        ArtistAvailabilityBlock.add(artist_id=profile.artist_id, block_date='2026-10-02')
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']), 2)

    def test_get_all_blocks_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 401)


# ─── Onboarding — Documents ────────────────────────────────────────────────────

class ArtistDocumentTest(TestCase):
    create_url = '/artists/documents/create/'
    delete_url = '/artists/documents/delete/'
    get_url = '/artists/documents/get/'
    get_all_url = '/artists/documents/get_all/'

    def _make_file(self, name='id.jpg'):
        return SimpleUploadedFile(name, make_image_bytes('JPEG'), content_type='image/jpeg')

    def _make_document(self, profile):
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        return ArtistDocument.objects.create(
            artist=profile, document_type='id_proof', file='artist_documents/test.jpg',
            verification_status=pending,
        )

    def test_create_document_returns_201(self):
        client, user = make_authenticated_client()
        resp = client.post(self.create_url, {
            **ID_PROOF_FORM, 'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('document_id', resp.data['data'])

    def test_create_document_invalid_type_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.post(self.create_url, {
            'document_type': 'passport', 'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_create_document_missing_file_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.post(self.create_url, {'document_type': 'id_proof'}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_create_document_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.post(self.create_url, {
            'document_type': 'id_proof', 'file': self._make_file(),
        }, format='multipart')
        self.assertEqual(resp.status_code, 401)

    def test_get_another_artists_document_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919000000300')
        _, user2 = make_authenticated_client(phone_number='+919000000301')
        doc = self._make_document(get_artist_profile(user2))
        resp = client.get(self.get_url, {'document_id': doc.document_id})
        self.assertEqual(resp.status_code, 400)

    def test_delete_another_artists_document_returns_400(self):
        client, _ = make_authenticated_client(phone_number='+919000000302')
        _, user2 = make_authenticated_client(phone_number='+919000000303')
        doc = self._make_document(get_artist_profile(user2))
        resp = client.delete(f'{self.delete_url}?document_id={doc.document_id}')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(ArtistDocument.objects.filter(document_id=doc.document_id).exists())

    def test_delete_own_document_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919000000304')
        doc = self._make_document(get_artist_profile(user))
        resp = client.delete(f'{self.delete_url}?document_id={doc.document_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ArtistDocument.objects.filter(document_id=doc.document_id).exists())

    def test_get_all_documents_returns_200(self):
        client, user = make_authenticated_client(phone_number='+919000000305')
        self._make_document(get_artist_profile(user))
        resp = client.get(self.get_all_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['data']['data']), 1)


# ─── Onboarding — Payout Account ───────────────────────────────────────────────

class ArtistPayoutAccountTest(TestCase):
    set_url = '/artists/payout_account/set/'
    get_url = '/artists/payout_account/get/'

    def test_set_payout_account_returns_200(self):
        client, user = make_authenticated_client()
        resp = client.put(self.set_url, {
            'account_holder_name': 'Test Artist',
            'bank_account_number': '123456789012',
            'ifsc_code': 'HDFC0001234',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        profile = get_artist_profile(user)
        self.assertTrue(ArtistPayoutAccount.objects.filter(artist=profile).exists())

    def test_set_payout_account_invalid_ifsc_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.put(self.set_url, {
            'account_holder_name': 'Test Artist',
            'bank_account_number': '123456789012',
            'ifsc_code': 'BADCODE',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_set_payout_account_short_account_number_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.put(self.set_url, {
            'account_holder_name': 'Test Artist',
            'bank_account_number': '123',
            'ifsc_code': 'HDFC0001234',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_set_payout_account_is_upsert_not_duplicate(self):
        client, user = make_authenticated_client()
        client.put(self.set_url, {
            'account_holder_name': 'A', 'bank_account_number': '111122223333', 'ifsc_code': 'HDFC0001234',
        }, format='json')
        client.put(self.set_url, {
            'account_holder_name': 'B', 'bank_account_number': '999988887777', 'ifsc_code': 'ICIC0005678',
        }, format='json')
        profile = get_artist_profile(user)
        self.assertEqual(ArtistPayoutAccount.objects.filter(artist=profile).count(), 1)
        self.assertEqual(ArtistPayoutAccount.objects.get(artist=profile).account_holder_name, 'B')

    def test_get_payout_account_masks_bank_account_number(self):
        client, user = make_authenticated_client()
        client.put(self.set_url, {
            'account_holder_name': 'Test Artist', 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234',
        }, format='json')
        resp = client.get(self.get_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['bankAccountNumberMasked'], 'XXXXXXXX9012')
        self.assertNotIn('bankAccountNumber', resp.data['data'])
        self.assertNotIn('123456789012', str(resp.data))

    def test_get_payout_account_before_set_returns_400(self):
        client, _ = make_authenticated_client()
        resp = client.get(self.get_url)
        self.assertEqual(resp.status_code, 400)


# ─── Onboarding — Agreement ─────────────────────────────────────────────────────

class ArtistAgreementTest(TestCase):
    url = '/artists/profile/agreement/accept/'

    def test_accept_agreement_returns_200(self):
        client, user = make_authenticated_client()
        resp = client.put(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200)
        profile = get_artist_profile(user)
        self.assertIsNotNone(profile.terms_accepted_at)


# ─── Onboarding — Status & Submit ───────────────────────────────────────────────

class ArtistOnboardingStatusTest(TestCase):
    status_url = '/artists/onboarding/status/'
    submit_url = '/artists/onboarding/submit/'

    def test_status_not_started_by_default(self):
        client, user = make_authenticated_client(phone_number='+919000000400')
        resp = client.get(self.status_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['status'], 'not_started')
        self.assertFalse(any(resp.data['data']['steps'].values()))

    def test_status_in_progress_after_partial_completion(self):
        client, user = make_authenticated_client(phone_number='+919000000401')
        client.put('/artists/profile/agreement/accept/', {}, format='json')
        resp = client.get(self.status_url)
        self.assertEqual(resp.data['data']['status'], 'in_progress')
        self.assertTrue(resp.data['data']['steps']['agreement'])
        self.assertFalse(resp.data['data']['steps']['documents'])

    def test_submit_with_missing_steps_returns_400_and_lists_them(self):
        client, user = make_authenticated_client(phone_number='+919000000402')
        resp = client.post(self.submit_url, {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(len(resp.data['error']) > 0)

    def test_submit_after_all_steps_returns_200_and_status_submitted(self):
        client, user = make_authenticated_client(phone_number='+919000000403')
        complete_onboarding_steps(client, user)
        resp = client.post(self.submit_url, {}, format='json')
        self.assertEqual(resp.status_code, 200)
        status_resp = client.get(self.status_url)
        self.assertEqual(status_resp.data['data']['status'], 'submitted')
        self.assertTrue(all(status_resp.data['data']['steps'].values()))
        self.assertIsNotNone(status_resp.data['data']['submittedForReviewAt'])

    def test_submit_when_already_approved_returns_400(self):
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        client, user = make_authenticated_client(phone_number='+919000000404')
        profile = complete_onboarding_steps(client, user)
        profile.approval_status = approved
        profile.save()
        resp = client.post(self.submit_url, {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_resubmit_after_rejection_reenters_pending_and_clears_reason(self):
        ApprovalStatus.objects.get_or_create(name='rejected', defaults={'description': 'Rejected'})
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        client, user = make_authenticated_client(phone_number='+919000000405')
        profile = complete_onboarding_steps(client, user)
        profile.approval_status = ApprovalStatus.objects.get(name='rejected')
        profile.rejection_reason = 'Blurry ID photo'
        profile.submitted_for_review_at = None
        profile.save()

        resp = client.post(self.submit_url, {}, format='json')
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, pending.status_id)
        self.assertIsNone(profile.rejection_reason)
        self.assertIsNotNone(profile.submitted_for_review_at)

        status_resp = client.get(self.status_url)
        self.assertEqual(status_resp.data['data']['status'], 'submitted')

    def test_editing_services_after_approval_keeps_approval_and_submission_state(self):
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        client, user = make_authenticated_client(phone_number='+919000000406')
        profile = complete_onboarding_steps(client, user)
        profile.approval_status = approved
        profile.submitted_for_review_at = timezone.now()
        profile.save()

        another_sub = make_sub_category(category=make_category(name='Second Category'), name='Second Service')
        resp = client.post('/artists/services/add/', {'sub_category_id': another_sub.sub_category_id}, format='json')
        self.assertEqual(resp.status_code, 201)
        profile.refresh_from_db()
        # Owner decision (Q-4): service edits never demote an approved artist.
        self.assertEqual(profile.approval_status_id, approved.status_id)
        self.assertIsNotNone(profile.submitted_for_review_at)

    def test_submit_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.post(self.submit_url, {}, format='json')
        self.assertEqual(resp.status_code, 401)



# ─── Upload validation & private KYC storage ──────────────────────────────────

class UploadValidationTest(TestCase):
    doc_url = '/artists/documents/create/'
    portfolio_url = '/artists/portfolio/create/'

    def _post_doc(self, client, upload):
        return client.post(self.doc_url, {**ID_PROOF_FORM, 'file': upload}, format='multipart')

    def test_html_file_rejected_as_document(self):
        client, _ = make_authenticated_client(phone_number='+919000000600')
        upload = SimpleUploadedFile('evil.html', b'<script>alert(1)</script>', content_type='text/html')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)
        self.assertEqual(ArtistDocument.objects.count(), 0)

    def test_fake_image_bytes_rejected_even_with_image_content_type(self):
        client, _ = make_authenticated_client(phone_number='+919000000601')
        upload = SimpleUploadedFile('id.jpg', b'fake-bytes', content_type='image/jpeg')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_extension_must_match_detected_format(self):
        client, _ = make_authenticated_client(phone_number='+919000000602')
        upload = SimpleUploadedFile('id.png', make_image_bytes('JPEG'), content_type='image/png')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_html_disguised_as_png_rejected(self):
        client, _ = make_authenticated_client(phone_number='+919000000603')
        upload = SimpleUploadedFile('id.png', b'<html></html>', content_type='image/png')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_oversized_document_rejected(self):
        client, _ = make_authenticated_client(phone_number='+919000000604')
        upload = SimpleUploadedFile('big.png', make_image_bytes('PNG') + b'0' * (5 * 1024 * 1024 + 1),
                                    content_type='image/png')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_large_valid_upload_is_not_crashed_by_request_copying(self):
        # >2.5 MB uploads are spooled to a temp file; copying request.data used to raise
        # "cannot pickle BufferedRandom" before any validation ran.
        client, _ = make_authenticated_client(phone_number='+919000000611')
        upload = SimpleUploadedFile('big.png', make_image_bytes('PNG') + b'0' * (3 * 1024 * 1024),
                                    content_type='image/png')
        self.assertEqual(self._post_doc(client, upload).status_code, 201)

    def test_empty_file_rejected(self):
        client, _ = make_authenticated_client(phone_number='+919000000605')
        upload = SimpleUploadedFile('empty.png', b'', content_type='image/png')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_valid_pdf_accepted_as_document(self):
        client, _ = make_authenticated_client(phone_number='+919000000606')
        upload = SimpleUploadedFile('id.pdf', b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n', content_type='application/pdf')
        self.assertEqual(self._post_doc(client, upload).status_code, 201)

    def test_fake_pdf_rejected(self):
        client, _ = make_authenticated_client(phone_number='+919000000607')
        upload = SimpleUploadedFile('id.pdf', b'not a pdf at all', content_type='application/pdf')
        self.assertEqual(self._post_doc(client, upload).status_code, 400)

    def test_portfolio_rejects_html_and_fake_image(self):
        client, _ = make_authenticated_client(phone_number='+919000000608')
        sub = make_sub_category()
        for name, content in (('x.html', b'<script></script>'), ('x.jpg', b'fakeimagecontent')):
            resp = client.post(self.portfolio_url, {
                'media_type': 'image', 'sub_category_id': sub.sub_category_id,
                'file': SimpleUploadedFile(name, content, content_type='image/jpeg'),
            }, format='multipart')
            self.assertEqual(resp.status_code, 400, name)
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_portfolio_video_requires_real_container_header(self):
        client, _ = make_authenticated_client(phone_number='+919000000609')
        sub = make_sub_category()
        fake = client.post(self.portfolio_url, {
            'media_type': 'video', 'sub_category_id': sub.sub_category_id,
            'file': SimpleUploadedFile('v.mp4', b'not-a-video-at-all', content_type='video/mp4'),
        }, format='multipart')
        self.assertEqual(fake.status_code, 400)
        real = client.post(self.portfolio_url, {
            'media_type': 'video', 'sub_category_id': sub.sub_category_id,
            'file': SimpleUploadedFile('v.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 32, content_type='video/mp4'),
        }, format='multipart')
        self.assertEqual(real.status_code, 201)

    def test_stored_file_names_are_randomised(self):
        client, user = make_authenticated_client(phone_number='+919000000610')
        resp = self._post_doc(client, SimpleUploadedFile('my-aadhaar-card.png', make_image_bytes('PNG'),
                                                          content_type='image/png'))
        self.assertEqual(resp.status_code, 201)
        stored = ArtistDocument.objects.get(document_id=resp.data['data']['document_id']).file.name
        self.assertNotIn('aadhaar', stored)
        self.assertTrue(stored.endswith('.png'))


class KycFilePrivacyTest(TestCase):
    def _upload(self, client):
        resp = client.post('/artists/documents/create/', {
            **ID_PROOF_FORM,
            'file': SimpleUploadedFile('id.png', make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 201)
        return resp.data['data']['document_id']

    def test_file_is_stored_outside_public_media_root(self):
        import os
        from django.conf import settings
        client, _ = make_authenticated_client(phone_number='+919000000620')
        document = ArtistDocument.objects.get(document_id=self._upload(client))
        self.assertTrue(os.path.exists(os.path.join(settings.PRIVATE_MEDIA_ROOT, document.file.name)))
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, document.file.name)))
        with self.assertRaises(ValueError):
            document.file.url

    def test_api_returns_download_route_not_storage_path(self):
        client, _ = make_authenticated_client(phone_number='+919000000621')
        document_id = self._upload(client)
        data = client.get('/artists/documents/get/', {'document_id': document_id}).data['data']
        self.assertEqual(data['fileUrl'], f'/artists/documents/file/?document_id={document_id}')
        listed = client.get('/artists/documents/get_all/').data['data']['data'][0]
        self.assertEqual(listed['fileUrl'], f'/artists/documents/file/?document_id={document_id}')

    def test_owner_can_download_with_safe_headers(self):
        client, _ = make_authenticated_client(phone_number='+919000000622')
        document_id = self._upload(client)
        resp = client.get('/artists/documents/file/', {'document_id': document_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', resp['Cache-Control'])
        self.assertEqual(b''.join(resp.streaming_content), make_image_bytes('PNG'))

    def test_admin_can_download_any_document(self):
        client, _ = make_authenticated_client(phone_number='+919000000623')
        document_id = self._upload(client)
        admin_client, _ = make_authenticated_client(phone_number='+919000000624', role='admin')
        self.assertEqual(admin_client.get('/artists/documents/file/', {'document_id': document_id}).status_code, 200)

    def test_other_artist_and_customer_cannot_download(self):
        client, _ = make_authenticated_client(phone_number='+919000000625')
        document_id = self._upload(client)
        other_artist, _ = make_authenticated_client(phone_number='+919000000626')
        customer, _ = make_authenticated_client(phone_number='+919000000627', role='customer')
        for other in (other_artist, customer):
            self.assertEqual(other.get('/artists/documents/file/', {'document_id': document_id}).status_code, 400)

    def test_download_unauthenticated_returns_401(self):
        client, _ = make_authenticated_client(phone_number='+919000000628')
        document_id = self._upload(client)
        self.assertEqual(APIClient().get('/artists/documents/file/', {'document_id': document_id}).status_code, 401)

    def test_legacy_html_file_is_forced_to_download_as_octet_stream(self):
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage  # noqa: F401 (public storage must stay untouched)
        client, user = make_authenticated_client(phone_number='+919000000629')
        profile = get_artist_profile(user)
        document = ArtistDocument(artist=profile, document_type='id_proof')
        document.file.save('legacy.html', ContentFile(b'<script>alert(1)</script>'), save=False)
        document.save()
        resp = client.get('/artists/documents/file/', {'document_id': document.document_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/octet-stream')
        self.assertTrue(resp['Content-Disposition'].startswith('attachment'))

    def test_move_kyc_files_command_moves_public_files_to_private(self):
        import os
        from django.conf import settings
        from django.core.management import call_command
        client, user = make_authenticated_client(phone_number='+919000000630')
        profile = get_artist_profile(user)
        name = 'artist_documents/artist_legacy/old.png'
        public_path = os.path.join(settings.MEDIA_ROOT, name)
        os.makedirs(os.path.dirname(public_path), exist_ok=True)
        with open(public_path, 'wb') as handle:
            handle.write(make_image_bytes('PNG'))
        ArtistDocument.objects.create(artist=profile, document_type='id_proof', file=name)
        call_command('move_kyc_files_to_private', stdout=io.StringIO())
        self.assertFalse(os.path.exists(public_path))
        self.assertTrue(os.path.exists(os.path.join(settings.PRIVATE_MEDIA_ROOT, name)))



# ─── KYC ID types ─────────────────────────────────────────────────────────────

class KycIdTypeTest(TestCase):
    url = '/artists/documents/create/'

    def _post(self, client, back=False, **fields):
        payload = {'document_type': 'id_proof', **fields,
                   'file': SimpleUploadedFile('f.png', make_image_bytes('PNG'), content_type='image/png')}
        if back:
            payload['back_file'] = SimpleUploadedFile('b.png', make_image_bytes('PNG'), content_type='image/png')
        return client.post(self.url, payload, format='multipart')

    def test_each_id_type_accepts_a_valid_number(self):
        cases = [
            ('aadhaar', '2345 6789 0123', True),
            ('voter_id', 'abc1234567', True),
            ('passport', 'K1234567', False),
            ('driving_licence', 'MH12-2011-0012345', True),
        ]
        for index, (id_type, number, needs_back) in enumerate(cases):
            client, _ = make_authenticated_client(phone_number=f'+91900000080{index}')
            resp = self._post(client, back=needs_back, id_type=id_type, document_number=number)
            self.assertEqual(resp.status_code, 201, (id_type, resp.data))

    def test_invalid_numbers_rejected_per_type(self):
        client, _ = make_authenticated_client(phone_number='+919000000810')
        for id_type, number in [('aadhaar', '123456789012'), ('aadhaar', '2345'), ('voter_id', '12345'),
                                ('passport', 'Z1234567'), ('driving_licence', 'XX')]:
            resp = self._post(client, back=True, id_type=id_type, document_number=number)
            self.assertEqual(resp.status_code, 400, (id_type, number))
        self.assertEqual(ArtistDocument.objects.count(), 0)

    def test_id_type_and_number_required_for_id_proof(self):
        client, _ = make_authenticated_client(phone_number='+919000000811')
        self.assertEqual(self._post(client, document_number='K1234567').status_code, 400)
        self.assertEqual(self._post(client, id_type='passport').status_code, 400)
        self.assertEqual(self._post(client, id_type='national_id', document_number='K1234567').status_code, 400)

    def test_back_image_required_except_for_passport(self):
        client, _ = make_authenticated_client(phone_number='+919000000812')
        self.assertEqual(self._post(client, id_type='aadhaar', document_number='234567890123').status_code, 400)
        self.assertEqual(self._post(client, id_type='voter_id', document_number='ABC1234567').status_code, 400)
        self.assertEqual(self._post(client, id_type='passport', document_number='K1234567').status_code, 201)

    def test_back_image_is_validated_and_served_by_side(self):
        client, _ = make_authenticated_client(phone_number='+919000000813')
        bad = client.post(self.url, {
            'document_type': 'id_proof', 'id_type': 'aadhaar', 'document_number': '234567890123',
            'file': SimpleUploadedFile('f.png', make_image_bytes('PNG'), content_type='image/png'),
            'back_file': SimpleUploadedFile('b.html', b'<html>', content_type='text/html'),
        }, format='multipart')
        self.assertEqual(bad.status_code, 400)
        ok = self._post(client, back=True, id_type='aadhaar', document_number='234567890123')
        document_id = ok.data['data']['document_id']
        data = client.get('/artists/documents/get/', {'document_id': document_id}).data['data']
        self.assertEqual(data['idType'], 'aadhaar')
        self.assertEqual(data['backFileUrl'], f'/artists/documents/file/?document_id={document_id}&side=back')
        back = client.get('/artists/documents/file/', {'document_id': document_id, 'side': 'back'})
        self.assertEqual(back.status_code, 200)

    def test_back_side_of_passport_without_back_file_is_404_style_400(self):
        client, _ = make_authenticated_client(phone_number='+919000000814')
        document_id = self._post(client, id_type='passport', document_number='K1234567').data['data']['document_id']
        self.assertEqual(client.get('/artists/documents/file/', {'document_id': document_id, 'side': 'back'}).status_code, 400)

    def test_aadhaar_is_never_stored_in_full_and_others_are_encrypted(self):
        from sunndari_apps.common.crypto import decrypt_text
        client, _ = make_authenticated_client(phone_number='+919000000815')
        aadhaar = ArtistDocument.objects.get(
            document_id=self._post(client, back=True, id_type='aadhaar', document_number='234567890123').data['data']['document_id'])
        self.assertEqual(aadhaar.document_number, 'XXXXXXXX0123')
        self.assertIsNone(aadhaar.document_number_encrypted)
        client2, _ = make_authenticated_client(phone_number='+919000000816')
        passport = ArtistDocument.objects.get(
            document_id=self._post(client2, id_type='passport', document_number='K1234567').data['data']['document_id'])
        self.assertNotIn('K1234567', passport.document_number_encrypted)
        self.assertEqual(decrypt_text(passport.document_number_encrypted), 'K1234567')
        self.assertEqual(passport.document_number, 'XXXX4567')

    def test_address_proof_rejects_id_type_and_back_file(self):
        client, _ = make_authenticated_client(phone_number='+919000000817')
        resp = client.post(self.url, {
            'document_type': 'address_proof', 'id_type': 'passport',
            'file': SimpleUploadedFile('f.png', make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 400)
        resp = client.post(self.url, {
            'document_type': 'address_proof',
            'file': SimpleUploadedFile('f.png', make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 201)

    def test_new_id_proof_replaces_previous_and_deletes_its_files(self):
        import os
        from django.conf import settings
        client, user = make_authenticated_client(phone_number='+919000000818')
        first = ArtistDocument.objects.get(
            document_id=self._post(client, id_type='passport', document_number='K1234567').data['data']['document_id'])
        first_path = os.path.join(settings.PRIVATE_MEDIA_ROOT, first.file.name)
        self.assertTrue(os.path.exists(first_path))
        self._post(client, back=True, id_type='aadhaar', document_number='234567890123')
        rows = ArtistDocument.objects.filter(artist=get_artist_profile(user), document_type='id_proof')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().id_type, 'aadhaar')
        self.assertFalse(os.path.exists(first_path))

    def test_deleting_document_removes_stored_files(self):
        import os
        from django.conf import settings
        client, _ = make_authenticated_client(phone_number='+919000000819')
        document_id = self._post(client, back=True, id_type='aadhaar', document_number='234567890123').data['data']['document_id']
        document = ArtistDocument.objects.get(document_id=document_id)
        paths = [os.path.join(settings.PRIVATE_MEDIA_ROOT, document.file.name),
                 os.path.join(settings.PRIVATE_MEDIA_ROOT, document.back_file.name)]
        self.assertEqual(client.delete(f'/artists/documents/delete/?document_id={document_id}').status_code, 200)
        self.assertFalse(any(os.path.exists(path) for path in paths))



# ─── Registration fields, specialities, work samples ──────────────────────────

class ArtistRegistrationFieldsTest(TestCase):
    update_url = '/artists/profile/update/'
    get_url = '/artists/profile/get/'

    def test_update_and_get_new_profile_fields(self):
        client, _ = make_authenticated_client(phone_number='+919000000900')
        resp = client.put(self.update_url, {
            'display_name': 'Glam by Asha', 'date_of_birth': '1994-02-10',
            'instagram_url': 'https://www.instagram.com/glam.by.asha', 'profile_type': 'studio',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        data = client.get(self.get_url).data['data']
        self.assertEqual(data['displayName'], 'Glam by Asha')
        self.assertEqual(data['dateOfBirth'], '1994-02-10')
        self.assertEqual(data['instagramUrl'], 'https://www.instagram.com/glam.by.asha')
        self.assertEqual(data['profileType'], 'studio')
        self.assertEqual(data['specialities'], [])

    def test_validation_rejects_bad_values(self):
        client, _ = make_authenticated_client(phone_number='+919000000901')
        too_young = (timezone.now().date().replace(year=timezone.now().year - 17)).isoformat()
        for payload in (
            {'date_of_birth': too_young},
            {'date_of_birth': '2999-01-01'},
            {'date_of_birth': '1800-01-01'},
            {'instagram_url': 'https://evil.com/asha'},
            {'instagram_url': 'http://instagram.com/asha'},
            {'instagram_url': 'https://instagram.com/asha/../x'},
            {'profile_type': 'agency'},
        ):
            self.assertEqual(client.put(self.update_url, payload, format='json').status_code, 400, payload)

    def test_other_users_never_see_date_of_birth_but_see_public_new_fields(self):
        artist_client, artist = make_authenticated_client(phone_number='+919000000902')
        artist_client.put(self.update_url, {
            'display_name': 'Glam', 'date_of_birth': '1994-02-10', 'profile_type': 'freelance',
        }, format='json')
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        profile = get_artist_profile(artist)
        profile.approval_status = approved
        profile.save()
        customer, _ = make_authenticated_client(phone_number='+919000000903', role='customer')
        data = customer.get(self.get_url, {'artist_id': profile.artist_id}).data['data']
        self.assertEqual(data['displayName'], 'Glam')
        self.assertEqual(data['profileType'], 'freelance')
        self.assertNotIn('dateOfBirth', data)
        resp = customer.get(self.get_url, {'artist_id': profile.artist_id, 'values': 'artistId,dateOfBirth'})
        self.assertEqual(resp.status_code, 400)

    def test_customer_artist_detail_exposes_display_name_but_not_date_of_birth_or_work_samples(self):
        artist_client, artist = make_authenticated_client(phone_number='+919000000904')
        sub = make_sub_category()
        artist_client.put(self.update_url, {'display_name': 'Glam', 'date_of_birth': '1994-02-10'}, format='json')
        artist_client.post('/artists/portfolio/create/', {
            'media_type': 'image', 'sub_category_id': sub.sub_category_id, 'is_work_sample': 'true',
            'file': SimpleUploadedFile('w.png', make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        profile = get_artist_profile(artist)
        profile.approval_status = approved
        profile.save()
        customer, _ = make_authenticated_client(phone_number='+919000000905', role='customer')
        data = customer.get('/customers/artists/get/', {'artist_id': profile.artist_id}).data['data']
        self.assertEqual(data['profile']['displayName'], 'Glam')
        self.assertNotIn('dateOfBirth', data['profile'])
        self.assertEqual(data['portfolio'], [])


class ArtistSpecialityTest(TestCase):
    set_url = '/artists/profile/specialities/set/'
    get_url = '/artists/profile/specialities/get_all/'

    def _artist_with_services(self, phone, count=2):
        client, user = make_authenticated_client(phone_number=phone)
        category = make_category(name=f'Cat {phone}')
        subs = [make_sub_category(category=category, name=f'Svc {i} {phone}') for i in range(count)]
        for sub in subs:
            client.post('/artists/services/add/', {'sub_category_id': sub.sub_category_id}, format='json')
        return client, user, subs

    def test_set_and_get_specialities(self):
        client, _, subs = self._artist_with_services('+919000000910')
        resp = client.put(self.set_url, {'sub_category_ids': [subs[0].sub_category_id]}, format='json')
        self.assertEqual(resp.status_code, 200)
        listed = client.get(self.get_url).data['data']
        self.assertEqual([row['subCategoryId'] for row in listed], [subs[0].sub_category_id])
        self.assertEqual(client.get('/artists/profile/get/').data['data']['specialities'], [subs[0].sub_category_id])

    def test_set_replaces_and_empty_clears(self):
        client, _, subs = self._artist_with_services('+919000000911')
        client.put(self.set_url, {'sub_category_ids': [subs[0].sub_category_id]}, format='json')
        client.put(self.set_url, {'sub_category_ids': [subs[1].sub_category_id]}, format='json')
        self.assertEqual([r['subCategoryId'] for r in client.get(self.get_url).data['data']], [subs[1].sub_category_id])
        client.put(self.set_url, {'sub_category_ids': []}, format='json')
        self.assertEqual(client.get(self.get_url).data['data'], [])

    def test_speciality_must_be_an_offered_service(self):
        client, _, _ = self._artist_with_services('+919000000912', count=1)
        other = make_sub_category(category=make_category(name='Other'), name='Not offered')
        resp = client.put(self.set_url, {'sub_category_ids': [other.sub_category_id]}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_removing_a_service_removes_its_speciality(self):
        client, _, subs = self._artist_with_services('+919000000913')
        client.put(self.set_url, {'sub_category_ids': [s.sub_category_id for s in subs]}, format='json')
        client.delete(f'/artists/services/remove/?sub_category_id={subs[0].sub_category_id}')
        self.assertEqual([r['subCategoryId'] for r in client.get(self.get_url).data['data']], [subs[1].sub_category_id])

    def test_specialities_are_separate_from_services(self):
        client, _, subs = self._artist_with_services('+919000000914')
        client.put(self.set_url, {'sub_category_ids': [subs[0].sub_category_id]}, format='json')
        self.assertEqual(len(client.get('/artists/services/get_all/').data['data']), 2)

    def test_cannot_set_more_than_ten_or_unauthenticated(self):
        client, _, _ = self._artist_with_services('+919000000915', count=1)
        self.assertEqual(client.put(self.set_url, {'sub_category_ids': list(range(1, 12))}, format='json').status_code, 400)
        self.assertEqual(APIClient().put(self.set_url, {'sub_category_ids': []}, format='json').status_code, 401)


class WorkSampleTest(TestCase):
    url = '/artists/portfolio/create/'

    def _post(self, client, sub, sample, media_type='image', name='w.png'):
        return client.post(self.url, {
            'media_type': media_type, 'sub_category_id': sub.sub_category_id,
            'is_work_sample': 'true' if sample else 'false',
            'file': SimpleUploadedFile(name, make_image_bytes('PNG'), content_type='image/png'),
        }, format='multipart')

    def test_up_to_five_work_samples_then_rejected(self):
        client, user = make_authenticated_client(phone_number='+919000000920')
        sub = make_sub_category()
        for _ in range(5):
            self.assertEqual(self._post(client, sub, True).status_code, 201)
        self.assertEqual(self._post(client, sub, True).status_code, 400)
        self.assertEqual(Portfolio.objects.filter(artist=get_artist_profile(user), is_work_sample=True).count(), 5)

    def test_work_samples_do_not_count_toward_portfolio_limit_and_vice_versa(self):
        client, user = make_authenticated_client(phone_number='+919000000921')
        sub = make_sub_category()
        for _ in range(5):
            self._post(client, sub, True)
        profile = get_artist_profile(user)
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        for i in range(20):
            Portfolio.objects.create(artist=profile, file=f'p/{i}.png', media_type='image', sub_category=sub,
                                     approval_status=pending)
        self.assertEqual(self._post(client, sub, False).status_code, 400)
        self.assertEqual(Portfolio.count_work_samples(profile.artist_id), 5)

    def test_work_sample_must_be_image(self):
        client, _ = make_authenticated_client(phone_number='+919000000922')
        sub = make_sub_category()
        resp = client.post(self.url, {
            'media_type': 'video', 'sub_category_id': sub.sub_category_id, 'is_work_sample': 'true',
            'file': SimpleUploadedFile('v.mp4', b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 32, content_type='video/mp4'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_foreign_portfolio_listing_hides_work_samples_but_owner_sees_them(self):
        owner, user = make_authenticated_client(phone_number='+919000000923')
        sub = make_sub_category()
        self._post(owner, sub, True)
        self._post(owner, sub, False)
        profile = get_artist_profile(user)
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ArtistProfile.objects.filter(artist_id=profile.artist_id).update(approval_status=approved)
        other, _ = make_authenticated_client(phone_number='+919000000924', role='customer')
        foreign = other.get('/artists/portfolio/get_all/', {'artist_id': profile.artist_id}).data['data']['data']
        own = owner.get('/artists/portfolio/get_all/').data['data']['data']
        self.assertEqual(len(foreign), 1)
        self.assertFalse(foreign[0]['isWorkSample'])
        self.assertEqual(len(own), 2)


class OnboardingRegistrationStepsTest(TestCase):
    def test_new_steps_gate_submission(self):
        client, user = make_authenticated_client(phone_number='+919000000930')
        complete_onboarding_steps(client, user)
        steps = client.get('/artists/onboarding/status/').data['data']['steps']
        self.assertTrue(steps['registrationFields'])
        self.assertTrue(steps['workSamples'])
        Portfolio.objects.filter(artist=get_artist_profile(user)).update(is_work_sample=False)
        self.assertFalse(client.get('/artists/onboarding/status/').data['data']['steps']['workSamples'])
        resp = client.post('/artists/onboarding/submit/', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        ArtistProfile.objects.filter(user_id=user.user_id).update(display_name=None)
        self.assertFalse(client.get('/artists/onboarding/status/').data['data']['steps']['registrationFields'])



# ─── Profile & cover photos ───────────────────────────────────────────────────

class ArtistPhotoTest(TestCase):
    upload_url = '/artists/profile/photo/upload/'
    delete_url = '/artists/profile/photo/delete/'
    get_url = '/artists/profile/get/'

    def _png(self, name='p.png'):
        return SimpleUploadedFile(name, make_image_bytes('PNG'), content_type='image/png')

    def test_upload_persists_and_profile_get_returns_absolute_urls(self):
        import os
        from django.conf import settings
        client, user = make_authenticated_client(phone_number='+919000000940')
        resp = client.put(self.upload_url, {'profile_photo': self._png(), 'cover_photo': self._png('c.png')},
                          format='multipart')
        self.assertEqual(resp.status_code, 200)
        profile = get_artist_profile(user)
        self.assertTrue(profile.profile_photo.name.startswith(f'artist_photos/artist_{profile.artist_id}/'))
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, profile.profile_photo.name)))
        data = client.get(self.get_url).data['data']
        self.assertTrue(data['profilePhotoUrl'].startswith('http://testserver/'))
        self.assertTrue(data['profilePhotoUrl'].endswith(profile.profile_photo.name))
        self.assertTrue(data['coverPhotoUrl'].endswith(profile.cover_photo.name))

    def test_unset_photos_are_null(self):
        client, _ = make_authenticated_client(phone_number='+919000000941')
        data = client.get(self.get_url).data['data']
        self.assertIsNone(data['profilePhotoUrl'])
        self.assertIsNone(data['coverPhotoUrl'])

    def test_upload_only_one_leaves_the_other_untouched(self):
        client, user = make_authenticated_client(phone_number='+919000000942')
        client.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        before = get_artist_profile(user).profile_photo.name
        client.put(self.upload_url, {'cover_photo': self._png()}, format='multipart')
        profile = get_artist_profile(user)
        self.assertEqual(profile.profile_photo.name, before)
        self.assertTrue(profile.cover_photo)

    def test_replacing_a_photo_deletes_the_old_file(self):
        import os
        from django.conf import settings
        client, user = make_authenticated_client(phone_number='+919000000943')
        client.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        old = get_artist_profile(user).profile_photo.name
        client.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        new = get_artist_profile(user).profile_photo.name
        self.assertNotEqual(old, new)
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, old)))
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, new)))

    def test_invalid_uploads_rejected_and_nothing_saved(self):
        client, user = make_authenticated_client(phone_number='+919000000944')
        for bad in (SimpleUploadedFile('x.html', b'<html>', content_type='image/png'),
                    SimpleUploadedFile('x.png', b'not-an-image', content_type='image/png'),
                    SimpleUploadedFile('x.pdf', b'%PDF-1.4', content_type='application/pdf')):
            self.assertEqual(client.put(self.upload_url, {'profile_photo': bad}, format='multipart').status_code, 400)
        self.assertEqual(client.put(self.upload_url, {}, format='multipart').status_code, 400)
        self.assertFalse(get_artist_profile(user).profile_photo)

    def test_one_bad_file_prevents_saving_the_good_one(self):
        client, user = make_authenticated_client(phone_number='+919000000945')
        resp = client.put(self.upload_url, {
            'profile_photo': self._png(),
            'cover_photo': SimpleUploadedFile('x.png', b'nope', content_type='image/png'),
        }, format='multipart')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(get_artist_profile(user).profile_photo)

    def test_delete_photo_removes_file_and_reference(self):
        import os
        from django.conf import settings
        client, user = make_authenticated_client(phone_number='+919000000946')
        client.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        name = get_artist_profile(user).profile_photo.name
        self.assertEqual(client.delete(f'{self.delete_url}?kind=profile').status_code, 200)
        self.assertFalse(get_artist_profile(user).profile_photo)
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, name)))
        self.assertEqual(client.delete(f'{self.delete_url}?kind=profile').status_code, 400)
        self.assertEqual(client.delete(f'{self.delete_url}?kind=banner').status_code, 400)

    def test_user_can_only_change_their_own_photos(self):
        owner, owner_user = make_authenticated_client(phone_number='+919000000947')
        other, other_user = make_authenticated_client(phone_number='+919000000948')
        owner.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        before = get_artist_profile(owner_user).profile_photo.name
        other.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        other.delete(f'{self.delete_url}?kind=profile')
        self.assertEqual(get_artist_profile(owner_user).profile_photo.name, before)

    def test_customers_and_unauthenticated_cannot_upload(self):
        customer, _ = make_authenticated_client(phone_number='+919000000949', role='customer')
        self.assertEqual(customer.put(self.upload_url, {'profile_photo': self._png()}, format='multipart').status_code, 400)
        self.assertEqual(APIClient().put(self.upload_url, {'profile_photo': self._png()}, format='multipart').status_code, 401)

    def test_other_users_see_photos_of_approved_artist(self):
        client, user = make_authenticated_client(phone_number='+919000000950')
        client.put(self.upload_url, {'profile_photo': self._png()}, format='multipart')
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ArtistProfile.objects.filter(user_id=user.user_id).update(approval_status=approved)
        customer, _ = make_authenticated_client(phone_number='+919000000951', role='customer')
        data = customer.get(self.get_url, {'artist_id': get_artist_profile(user).artist_id}).data['data']
        self.assertTrue(data['profilePhotoUrl'].startswith('http://testserver/'))
        self.assertIsNone(data['coverPhotoUrl'])



# ─── Package extras ───────────────────────────────────────────────────────────

class PackageExtrasTest(TestCase):
    create_url = '/artists/packages/create/'
    update_url = '/artists/packages/update/'
    get_url = '/artists/packages/get/'
    get_all_url = '/artists/packages/get_all/'
    photo_url = '/artists/packages/photo/upload/'
    photo_delete_url = '/artists/packages/photo/delete/'

    def _create(self, client, sub, **extra):
        return client.post(self.create_url, {
            'sub_category_id': sub.sub_category_id, 'name': 'Bridal', 'price': '3000.00', 'duration_minutes': 90,
            **extra,
        }, format='json')

    def test_create_with_extras_and_read_back_with_derived_category(self):
        client, _ = make_authenticated_client(phone_number='+919000001000')
        sub = make_sub_category(category=make_category(name='Makeup'), name='Bridal Makeup')
        resp = self._create(client, sub, makeup_type='HD', brands=['MAC', 'Huda Beauty'], product_details='Airbrush, waterproof')
        self.assertEqual(resp.status_code, 201)
        data = client.get(self.get_url, {'package_id': resp.data['data']['package_id']}).data['data']
        self.assertEqual(data['makeupType'], 'HD')
        self.assertEqual(data['brands'], ['MAC', 'Huda Beauty'])
        self.assertEqual(data['productDetails'], 'Airbrush, waterproof')
        self.assertIsNone(data['photoUrl'])
        self.assertEqual(data['category'], {'categoryId': sub.category_id, 'name': 'Makeup'})
        listed = client.get(self.get_all_url).data['data']['data'][0]
        self.assertEqual(listed['brands'], ['MAC', 'Huda Beauty'])
        self.assertEqual(listed['category']['name'], 'Makeup')

    def test_existing_clients_that_send_no_extras_still_work(self):
        client, _ = make_authenticated_client(phone_number='+919000001001')
        sub = make_sub_category()
        resp = self._create(client, sub)
        self.assertEqual(resp.status_code, 201)
        data = client.get(self.get_url, {'package_id': resp.data['data']['package_id']}).data['data']
        self.assertEqual(data['brands'], [])
        self.assertIsNone(data['makeupType'])

    def test_update_changes_only_sent_extras_and_can_clear_brands(self):
        client, _ = make_authenticated_client(phone_number='+919000001002')
        sub = make_sub_category()
        package_id = self._create(client, sub, makeup_type='HD', brands=['MAC']).data['data']['package_id']
        client.put(self.update_url, {'package_id': package_id, 'product_details': 'New kit'}, format='json')
        data = client.get(self.get_url, {'package_id': package_id}).data['data']
        self.assertEqual((data['makeupType'], data['brands'], data['productDetails']), ('HD', ['MAC'], 'New kit'))
        client.put(self.update_url, {'package_id': package_id, 'brands': []}, format='json')
        self.assertEqual(client.get(self.get_url, {'package_id': package_id}).data['data']['brands'], [])

    def test_brand_list_limits(self):
        client, _ = make_authenticated_client(phone_number='+919000001003')
        sub = make_sub_category()
        self.assertEqual(self._create(client, sub, brands=[f'b{i}' for i in range(11)]).status_code, 400)
        self.assertEqual(self._create(client, sub, brands=['x' * 51]).status_code, 400)

    def test_photo_upload_replace_delete(self):
        import os
        from django.conf import settings
        client, user = make_authenticated_client(phone_number='+919000001004')
        sub = make_sub_category()
        package_id = self._create(client, sub).data['data']['package_id']

        def upload(name='s.png'):
            return client.put(self.photo_url, {
                'package_id': package_id,
                'photo': SimpleUploadedFile(name, make_image_bytes('PNG'), content_type='image/png'),
            }, format='multipart')
        self.assertEqual(upload().status_code, 200)
        first = PricingPackage.objects.get(package_id=package_id).photo.name
        self.assertTrue(first.startswith(f'package_photos/artist_{get_artist_profile(user).artist_id}/'))
        url = client.get(self.get_url, {'package_id': package_id}).data['data']['photoUrl']
        self.assertTrue(url.startswith('http://testserver/') and url.endswith(first))
        upload('t.png')
        second = PricingPackage.objects.get(package_id=package_id).photo.name
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, first)))
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, second)))
        self.assertEqual(client.delete(f'{self.photo_delete_url}?package_id={package_id}').status_code, 200)
        self.assertFalse(PricingPackage.objects.get(package_id=package_id).photo)
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, second)))
        self.assertEqual(client.delete(f'{self.photo_delete_url}?package_id={package_id}').status_code, 400)

    def test_photo_validation_and_ownership(self):
        owner, _ = make_authenticated_client(phone_number='+919000001005')
        other, _ = make_authenticated_client(phone_number='+919000001006')
        sub = make_sub_category()
        package_id = self._create(owner, sub).data['data']['package_id']
        bad = owner.put(self.photo_url, {
            'package_id': package_id, 'photo': SimpleUploadedFile('x.png', b'nope', content_type='image/png'),
        }, format='multipart')
        self.assertEqual(bad.status_code, 400)
        missing = owner.put(self.photo_url, {'package_id': package_id}, format='multipart')
        self.assertEqual(missing.status_code, 400)
        good_file = lambda: SimpleUploadedFile('s.png', make_image_bytes('PNG'), content_type='image/png')
        stolen = other.put(self.photo_url, {'package_id': package_id, 'photo': good_file()}, format='multipart')
        self.assertEqual(stolen.status_code, 400)
        self.assertFalse(PricingPackage.objects.get(package_id=package_id).photo)
        self.assertEqual(APIClient().put(self.photo_url, {'package_id': package_id, 'photo': good_file()},
                                         format='multipart').status_code, 401)

    def test_other_artist_cannot_edit_extras(self):
        owner, _ = make_authenticated_client(phone_number='+919000001007')
        other, _ = make_authenticated_client(phone_number='+919000001008')
        package_id = self._create(owner, make_sub_category()).data['data']['package_id']
        resp = other.put(self.update_url, {'package_id': package_id, 'makeup_type': 'Hacked'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(PricingPackage.objects.get(package_id=package_id).makeup_type)

    def test_customer_artist_detail_shows_extras(self):
        artist, user = make_authenticated_client(phone_number='+919000001009')
        sub = make_sub_category(category=make_category(name='Makeup2'), name='Party')
        self._create(artist, sub, makeup_type='Natural', brands=['Lakme'])
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        ArtistProfile.objects.filter(user_id=user.user_id).update(approval_status=approved)
        customer, _ = make_authenticated_client(phone_number='+919000001010', role='customer')
        pkg = customer.get('/customers/artists/get/', {'artist_id': get_artist_profile(user).artist_id}).data['data']['packages'][0]
        self.assertEqual((pkg['makeupType'], pkg['brands'], pkg['category']['name']), ('Natural', ['Lakme'], 'Makeup2'))



# ─── Payout account encryption, foreign list visibility, booking decision lock ─

class PayoutAccountEncryptionTest(TestCase):
    def test_account_number_is_encrypted_at_rest_but_masked_in_api(self):
        from sunndari_apps.notifications.models.notification import Notification
        client, user = make_authenticated_client(phone_number='+919000004000')
        resp = client.put('/artists/payout_account/set/', {
            'account_holder_name': 'Asha', 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        stored = ArtistPayoutAccount.objects.get(artist=get_artist_profile(user)).bank_account_number
        self.assertNotIn('123456789012', stored)
        self.assertTrue(stored.startswith('gAAAA'))
        data = client.get('/artists/payout_account/get/').data['data']
        self.assertEqual(data['bankAccountNumberMasked'], 'XXXXXXXX9012')
        self.assertNotIn('123456789012', str(data))
        self.assertTrue(Notification.objects.filter(user_id=user.user_id, type='payout_account_changed').exists())

    def test_changing_the_account_resets_verification_to_pending(self):
        client, user = make_authenticated_client(phone_number='+919000004001')
        approved, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        body = {'account_holder_name': 'Asha', 'bank_account_number': '123456789012', 'ifsc_code': 'HDFC0001234'}
        client.put('/artists/payout_account/set/', body, format='json')
        ArtistPayoutAccount.objects.filter(artist=get_artist_profile(user)).update(verification_status=approved)
        client.put('/artists/payout_account/set/', {**body, 'bank_account_number': '999988887777'}, format='json')
        account = ArtistPayoutAccount.objects.get(artist=get_artist_profile(user))
        self.assertEqual(account.verification_status.name, 'pending')
        self.assertEqual(client.get('/artists/payout_account/get/').data['data']['bankAccountNumberMasked'], 'XXXXXXXX7777')


class ForeignListVisibilityTest(TestCase):
    def _artist_with_content(self, phone, approved):
        client, user = make_authenticated_client(phone_number=phone)
        sub = make_sub_category(category=make_category(name=f'C{phone}'), name=f'S{phone}')
        profile = get_artist_profile(user)
        if approved:
            status, _ = ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
            profile.approval_status = status
            profile.save()
        active = PricingPackage.objects.create(artist=profile, sub_category=sub, name='Active', price=1000, duration_minutes=60)
        PricingPackage.objects.create(artist=profile, sub_category=sub, name='Hidden', price=1000, duration_minutes=60, is_active=False)
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        Portfolio.objects.create(artist=profile, file='p/a.png', media_type='image', sub_category=sub, approval_status=pending)
        Portfolio.objects.create(artist=profile, file='p/b.png', media_type='image', sub_category=sub,
                                 approval_status=pending, is_active=False)
        return client, profile

    def test_other_users_see_only_active_items_of_approved_artists(self):
        _, profile = self._artist_with_content('+919000004010', approved=True)
        viewer, _ = make_authenticated_client(phone_number='+919000004011', role='customer')
        packages = viewer.get('/artists/packages/get_all/', {'artist_id': profile.artist_id}).data['data']['data']
        portfolio = viewer.get('/artists/portfolio/get_all/', {'artist_id': profile.artist_id}).data['data']['data']
        self.assertEqual([p['name'] for p in packages], ['Active'])
        self.assertEqual(len(portfolio), 1)

    def test_other_users_cannot_list_items_of_unapproved_artists(self):
        _, profile = self._artist_with_content('+919000004012', approved=False)
        viewer, _ = make_authenticated_client(phone_number='+919000004013', role='customer')
        self.assertEqual(viewer.get('/artists/packages/get_all/', {'artist_id': profile.artist_id}).status_code, 400)
        self.assertEqual(viewer.get('/artists/portfolio/get_all/', {'artist_id': profile.artist_id}).status_code, 400)

    def test_owner_still_sees_everything_even_when_passing_own_artist_id(self):
        client, profile = self._artist_with_content('+919000004014', approved=False)
        self.assertEqual(len(client.get('/artists/packages/get_all/').data['data']['data']), 2)
        self.assertEqual(len(client.get('/artists/packages/get_all/', {'artist_id': profile.artist_id}).data['data']['data']), 2)
        self.assertEqual(len(client.get('/artists/portfolio/get_all/', {'artist_id': profile.artist_id}).data['data']['data']), 2)
