from django.test import TestCase

from sunndari_apps.artists.models import ArtistProfile, ArtistSpeciality
from sunndari_apps.authentication.models import User
from sunndari_apps.core.models import ApprovalStatus
from qa.harness import record, observe, blocked, unverified, body, data, is_2xx, dump, new_client, make_actor
from qa import world as w

F = 'PROFILE'


class ProfileQA(TestCase):
    def tearDown(self):
        dump()

    def test_account_takeover_chain_via_profile_leak(self):
        """Root-cause demonstration for the P0 profile leak, entirely inside the test DB."""
        w.seed_statuses()
        victim = w.make_customer('+919300000001', 'Victim')
        admin = w.make_admin('+919300000002')
        attacker = w.make_customer('+919300000003', 'Attacker')
        leaked = (data(attacker.client.get('/users/profile/get/', {'user_id': admin.id})) or {}).get('access_token')
        record('SECURITY', 'Attacker (plain customer) obtains the admin access token through /users/profile/get/', leaked is None, 'no token in response', f'token obtained={bool(leaked)}', sev='P0',
               note='User.get() selects access_token; UsersUtils mapper only renames known columns and passes the rest through')
        if leaked:
            hijacked = new_client(leaked)
            r = hijacked.get('/admin-panel/artists/review_queue/get_all/')
            record('SECURITY', 'Leaked admin token is accepted by admin endpoints (full privilege takeover)', not is_2xx(r), 'should be impossible', f'HTTP {r.status_code}', sev='P0')
            r = hijacked.get('/help_center/admin/conversations/get_all/')
            observe('SECURITY', 'Leaked admin token can read all help-center conversations', f'HTTP {r.status_code}', sev='P0')
            vtok = (data(attacker.client.get('/users/profile/get/', {'user_id': victim.id})) or {}).get('access_token')
            r = new_client(vtok).get('/users/address/get_all/')
            observe('SECURITY', "Leaked customer token accepted (act as the victim: addresses, bookings, wallet)", f'HTTP {r.status_code}', sev='P0')
        own = body(attacker.client.get('/users/profile/get/', {'user_id': attacker.id}))
        record('SECURITY', 'Own profile response should also not echo the bearer token', 'access_token' not in str(own), 'absent', sorted((own.get('data') or {})), sev='P1')

    def test_artist_profile_persistence_and_mass_assignment(self):
        w.seed_statuses()
        art = w.make_bookable_artist('+919300000010', 'Persist Artist', approved=False)
        art.user.set_password('Pass-word-123')
        art.user.save()
        other = w.make_bookable_artist('+919300000011', 'Other Artist')
        c = art.client
        addr = w.CustomerAddress.objects.get(address_id=w.CustomerAddress().create(user_id=art.id, address_line_1='9 Studio Rd', city='Lucknow', pin_code='226010'))
        r = c.put('/artists/profile/update/', {
            'display_name': 'Glam Persist', 'date_of_birth': '1992-03-04', 'instagram_url': 'https://instagram.com/glam.persist',
            'profile_type': 'studio', 'bio': 'Bridal and party makeup', 'years_experience': 6, 'city': 'Lucknow',
            'service_radius_km': 25, 'base_address_id': addr.address_id, 'travel_time_before_minutes': 30, 'return_buffer_minutes': 15,
        }, format='json')
        record(F, 'profile update accepts all registration fields', r.status_code == 200, 200, r.status_code, sev='P1')
        r = c.put('/artists/profile/specialities/set/', {'sub_category_ids': [art.sub.sub_category_id]}, format='json')
        record(F, 'specialities set', r.status_code == 200, 200, r.status_code, sev='P1')
        r = c.put('/artists/profile/photo/upload/', {'profile_photo': w.png('p.png'), 'cover_photo': w.png('c.png')}, format='multipart')
        record(F, 'profile + cover photo upload', r.status_code == 200, 200, r.status_code, sev='P1')
        r = c.post('/artists/portfolio/create/', {'media_type': 'image', 'sub_category_id': art.sub.sub_category_id, 'is_work_sample': 'true', 'file': w.png()}, format='multipart')
        record(F, 'work sample upload', r.status_code == 201, 201, r.status_code, sev='P1')
        before = data(c.get('/artists/profile/get/'))
        # full logout/login cycle through the real login endpoint
        login = new_client().post('/auth/login/', {'username': '+919300000010', 'password': 'Pass-word-123'})
        record(F, 'artist can log in again after profile setup', login.status_code == 200, 200, login.status_code, sev='P1')
        c = new_client(data(login)['access_token'])          # single-session design: the old token is now invalid
        after = data(c.get('/artists/profile/get/')) or {}
        expect = {'displayName': 'Glam Persist', 'dateOfBirth': '1992-03-04', 'instagramUrl': 'https://instagram.com/glam.persist', 'profileType': 'studio',
                  'bio': 'Bridal and party makeup', 'yearsExperience': 6, 'city': 'Lucknow', 'serviceRadiusKm': 25, 'baseAddressId': addr.address_id,
                  'travelTimeBeforeMinutes': 30, 'returnBufferMinutes': 15, 'specialities': [art.sub.sub_category_id]}
        missing = {k: (v, after.get(k)) for k, v in expect.items() if after.get(k) != v}
        record(F, 'every registration field survives logout/login', not missing, 'all persisted', missing or 'all present', sev='P1')
        record(F, 'profile + cover photo URLs returned after re-login', bool(after.get('profilePhotoUrl')) and bool(after.get('coverPhotoUrl')), 'both URLs', (after.get('profilePhotoUrl'), after.get('coverPhotoUrl')), sev='P1')
        from sunndari_apps.artists.models import Portfolio
        record(F, 'work sample persisted in DB', Portfolio.objects.filter(artist=art.profile, is_work_sample=True).count() == 1, 1, 'checked', sev='P1')
        # re-upload behaviour
        old = ArtistProfile.objects.get(artist_id=art.profile.artist_id).profile_photo.name
        c.put('/artists/profile/photo/upload/', {'profile_photo': w.png('p2.png')}, format='multipart')
        new = ArtistProfile.objects.get(artist_id=art.profile.artist_id).profile_photo.name
        import os
        from django.conf import settings
        record(F, 're-upload replaces photo and removes the old file', old != new and not os.path.exists(os.path.join(settings.MEDIA_ROOT, old)), 'replaced, old file gone', f'{old} -> {new}', sev='P3')
        # mass assignment
        approved = ApprovalStatus.objects.get(name='approved').status_id
        c.put('/artists/profile/update/', {'commission_rate': '0.00', 'approval_status_id': approved, 'avg_rating': '5.00', 'total_reviews': 999,
                                          'user_id': other.id, 'artist_id': other.profile.artist_id, 'public_slug': 'hijack', 'profile_view_count': 9999,
                                          'is_accepting_bookings': False, 'terms_accepted_at': '2020-01-01T00:00:00Z', 'rejection_reason': 'x', 'bio': 'ok'}, format='json')
        p = ArtistProfile.objects.get(artist_id=art.profile.artist_id)
        record('SECURITY', 'profile update ignores protected fields (commission, approval, rating, slug, counters, agreement)',
               p.commission_rate == 10 and p.approval_status.name == 'pending' and p.avg_rating == 0 and p.total_reviews == 0 and p.public_slug is None and p.profile_view_count == 0 and p.is_accepting_bookings and p.terms_accepted_at is None,
               'all unchanged', f'commission={p.commission_rate} status={p.approval_status.name} rating={p.avg_rating} reviews={p.total_reviews} slug={p.public_slug}', sev='P0')
        o = ArtistProfile.objects.get(artist_id=other.profile.artist_id)
        record('SECURITY', 'profile update with another artist_id/user_id does not touch that artist', o.bio != 'ok' and o.user_id == other.id, 'unchanged', o.bio, sev='P0')
        r = c.put('/users/profile/update/', {'name': 'Renamed', 'role': 'admin', 'is_active': False, 'access_token': 'x'}, format='json')
        u = User.objects.get(pk=art.id)
        record('SECURITY', 'user profile update cannot change role / is_active / token (mass assignment)', u.role == 'artist' and u.is_active and u.access_token != 'x', 'unchanged', f'role={u.role} active={u.is_active}', sev='P0')
        # state skipping through direct API
        r = c.post('/artists/onboarding/submit/', {}, format='json')
        record('APPROVAL', 'incomplete onboarding cannot be submitted', r.status_code == 400, 400, r.status_code, sev='P1')
        record('APPROVAL', 'artist cannot approve self via admin endpoint', not is_2xx(c.put('/admin-panel/artists/approve/', {'artist_id': art.profile.artist_id}, format='json')), 'rejected', 'checked', sev='P0')
        record('APPROVAL', 'artist cannot reject a competitor via admin endpoint', not is_2xx(c.put('/admin-panel/artists/reject/', {'artist_id': other.profile.artist_id, 'reason': 'x'}, format='json')), 'rejected', 'checked', sev='P0')
        record('APPROVAL', 'unapproved artist is hidden from customer search', all(a['artistId'] != art.profile.artist_id for a in (data(w.make_customer('+919300000012', 'Searcher').client.get('/customers/artists/search/')) or {}).get('data', [])), 'hidden', 'checked', sev='P1')
