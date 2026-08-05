import tempfile
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from sunndari_apps.authentication.models import User
from sunndari_apps.authentication.utils import generate_jwt_token
from sunndari_apps.artists.models import (
    ArtistProfile, ArtistServiceOffering, ArtistLocationPreference,
    Portfolio, PricingPackage, PackageInclusion,
    ArtistAvailabilitySchedule, ArtistAvailabilityBlock,
)
from sunndari_apps.core.models import ServiceSubCategory, ServiceCategory, LocationType, ApprovalStatus


# ─── Helpers ──────────────────────────────────────────────────────────────────

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

    def test_add_service_triggers_re_approval(self):
        ApprovalStatus.objects.get_or_create(name='approved', defaults={'description': 'Approved'})
        pending, _ = ApprovalStatus.objects.get_or_create(name='pending', defaults={'description': 'Pending'})
        client, user = make_authenticated_client()
        profile = get_artist_profile(user)
        profile.approval_status = ApprovalStatus.objects.get(name='approved')
        profile.save()

        sub = make_sub_category()
        client.post(self.add_url, {'sub_category_id': sub.sub_category_id})
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status_id, pending.status_id)

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

    def _make_file(self, name='test.jpg', content=b'fakeimagecontent'):
        return SimpleUploadedFile(name, content, content_type='image/jpeg')

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
